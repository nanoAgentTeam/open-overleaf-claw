#!/usr/bin/env python3
"""
Sync E2E test workspace fixtures to Overleaf.

For each workspace fixture, this script:
  1. Creates a new blank project on Overleaf
  2. Uploads all local fixture files to it
  3. Writes the Overleaf project ID back into the test case YAML (overleaf_id field)

Usage:
  .venv/bin/python tests/scripts/sync_to_overleaf.py                  # sync all
  .venv/bin/python tests/scripts/sync_to_overleaf.py w03 r01          # sync matching
  .venv/bin/python tests/scripts/sync_to_overleaf.py --list           # list Overleaf projects
  .venv/bin/python tests/scripts/sync_to_overleaf.py --dry-run        # show plan without executing
"""

import os
import sys
import json
import pickle
import time
import argparse
import re
import yaml
import requests
from pathlib import Path
from bs4 import BeautifulSoup

import pyoverleaf

# ── Overleaf client (single pyoverleaf.Api instance) ─────────────────────────

class OverleafClient:
    """Wrapper: one shared pyoverleaf.Api + a requests.Session for create."""

    BASE = "https://www.overleaf.com"

    def __init__(self, olauth_path: Path):
        cookie_data = pickle.load(open(olauth_path, "rb"))
        cookie_jar = cookie_data["cookie"]

        # pyoverleaf api (for list / upload / folder / delete)
        self.api = pyoverleaf.Api()
        self.api.login_from_cookies(cookie_jar)

        # requests session (for create_project which needs CSRF)
        self.session = requests.Session()
        self.session.cookies.update(cookie_jar)
        self._csrf: str | None = None

    # ── CSRF (only needed for create_project) ────────────────────────────

    def _fetch_csrf(self) -> str:
        if self._csrf:
            return self._csrf
        r = self.session.get(f"{self.BASE}/project")
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        meta = soup.find("meta", {"name": "ol-csrfToken"})
        if meta and meta.get("content"):
            self._csrf = meta["content"]
            return self._csrf
        m = re.search(r'window\.csrfToken\s*=\s*"([^"]+)"', r.text)
        if m:
            self._csrf = m.group(1)
            return self._csrf
        meta2 = soup.find("meta", {"name": "ol-prefetchedProjectsBlob"})
        if meta2 and meta2.get("content"):
            blob = json.loads(meta2["content"])
            if blob.get("csrfToken"):
                self._csrf = blob["csrfToken"]
                return self._csrf
        raise RuntimeError("Could not obtain CSRF token — cookie may be stale, re-run `ols login`.")

    # ── API wrappers ─────────────────────────────────────────────────────

    def list_projects(self) -> list[dict]:
        projects = self.api.get_projects()
        return [
            {"id": p.id, "name": p.name, "updated": str(getattr(p, "last_updated", ""))}
            for p in projects
        ]

    def create_project(self, name: str) -> str:
        """Create a blank project via requests (pyoverleaf has no create). Returns project ID."""
        headers = {
            "x-csrf-token": self._fetch_csrf(),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.BASE}/project",
            "Content-Type": "application/json",
        }
        resp = self.session.post(
            f"{self.BASE}/project/new",
            json={"projectName": name, "template": "blank"},
            headers=headers,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            pid = data.get("project_id") or data.get("id")
            if pid:
                return pid
        raise RuntimeError(f"create_project failed: HTTP {resp.status_code} — {resp.text[:200]}")

    def get_root_folder(self, project_id: str):
        return self.api.project_get_files(project_id)

    def upload_file(self, project_id: str, folder_id: str, filename: str, content: bytes):
        return self.api.project_upload_file(project_id, folder_id, filename, content)

    def create_folder(self, project_id: str, parent_id: str, folder_name: str):
        return self.api.project_create_folder(project_id, parent_id, folder_name)

    def delete_entity(self, project_id: str, entity):
        self.api.project_delete_entity(project_id, entity)

    def ensure_folder(self, project_id: str, root_folder, folder_path: str) -> str:
        """Walk / create nested folders, return leaf folder ID."""
        if not folder_path or folder_path == ".":
            return getattr(root_folder, "id")

        current = root_folder
        for part in folder_path.split("/"):
            found = None
            for child in getattr(current, "children", []):
                if getattr(child, "name", "") == part and hasattr(child, "children"):
                    found = child
                    break
            if found:
                current = found
            else:
                current = self.create_folder(project_id, getattr(current, "id"), part)
        return getattr(current, "id")


# ── Workspace discovery ───────────────────────────────────────────────────────

def discover_fixtures(workspace_root: Path, cases_dir: Path, patterns: list[str] | None,
                      include_hidden: bool = False) -> list[dict]:
    results = []
    for yaml_path in sorted(cases_dir.glob("*.yaml")):
        if patterns and not any(p.lower() in yaml_path.stem.lower() for p in patterns):
            continue
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        pid = cfg.get("project_id", "")
        fixture_dir = workspace_root / pid / pid
        if not fixture_dir.is_dir():
            continue

        files = []
        for root, dirs, fnames in os.walk(fixture_dir):
            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in fnames:
                if not include_hidden and fn.startswith("."):
                    continue
                full = Path(root) / fn
                files.append(str(full.relative_to(fixture_dir)))
        results.append({
            "case_yaml": yaml_path,
            "project_id": pid,
            "fixture_dir": fixture_dir,
            "files": files,
            "config": cfg,
        })
    return results


# ── Upload logic ──────────────────────────────────────────────────────────────

def upload_fixture(client: OverleafClient, overleaf_pid: str, fixture_dir: Path, files: list[str]) -> int:
    """Upload all fixture files. Returns uploaded count."""

    # Delete the default main.tex from the blank template
    root = client.get_root_folder(overleaf_pid)
    for child in getattr(root, "children", []):
        if getattr(child, "name", "") == "main.tex" and not hasattr(child, "children"):
            try:
                client.delete_entity(overleaf_pid, child)
                print(f"    Deleted default main.tex")
            except Exception:
                pass
            break

    # Re-fetch after deletion
    root = client.get_root_folder(overleaf_pid)
    root_id = getattr(root, "id")
    uploaded = 0

    for rel_path in sorted(files):
        local = fixture_dir / rel_path
        folder_part = os.path.dirname(rel_path)
        filename = os.path.basename(rel_path)

        if folder_part:
            folder_id = client.ensure_folder(overleaf_pid, root, folder_part)
            # Re-fetch tree so next ensure_folder sees the created folders
            root = client.get_root_folder(overleaf_pid)
        else:
            folder_id = root_id

        with open(local, "rb") as f:
            content = f.read()
        client.upload_file(overleaf_pid, folder_id, filename, content)
        uploaded += 1
        print(f"    [{uploaded}/{len(files)}] {rel_path}")

    return uploaded


def write_overleaf_id_to_yaml(yaml_path: Path, overleaf_id: str):
    """Insert or update overleaf_id in the case YAML."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = f.read()

    if re.search(r"^overleaf_id:", content, re.MULTILINE):
        content = re.sub(r'^overleaf_id:.*$', f'overleaf_id: "{overleaf_id}"', content, flags=re.MULTILINE)
    else:
        content = re.sub(
            r'^(project_id:.*?)$',
            rf'\1\noverleaf_id: "{overleaf_id}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(content)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync E2E workspace fixtures to Overleaf.")
    parser.add_argument("cases", nargs="*", help="Case name patterns (substring match). Omit = all.")
    parser.add_argument("--list", action="store_true", help="Just list Overleaf projects and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without creating/uploading.")
    parser.add_argument("--include-hidden", action="store_true", help="Also upload hidden files/dirs (e.g. .project_memory/).")
    parser.add_argument("--root", default=".", help="Project root directory.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    repo_root = Path(__file__).resolve().parent.parent
    olauth_candidates = [
        repo_root / ".olauth",
        root / ".olauth",
        Path.home() / ".olauth",
    ]
    olauth = next((p for p in olauth_candidates if p.exists()), None)
    if not olauth:
        print("ERROR: .olauth not found. Run `ols login` first.")
        sys.exit(1)

    client = OverleafClient(olauth)

    # ── --list mode ──
    if args.list:
        projects = client.list_projects()
        if not projects:
            print("No Overleaf projects found.")
        else:
            print(f"Found {len(projects)} project(s):")
            for p in projects:
                print(f"  [{p['updated'][:16]}] {p['name']}  (ID: {p['id']})")
        return

    # ── discover fixtures ──
    workspace = root / "workspace"
    cases_dir = root / "tests" / "cases"
    fixtures = discover_fixtures(workspace, cases_dir, args.cases or None,
                                 include_hidden=args.include_hidden)

    if not fixtures:
        print("No matching fixtures found.")
        return

    # Check existing Overleaf projects
    try:
        existing_projects = {p["name"]: p["id"] for p in client.list_projects()}
    except Exception:
        existing_projects = {}

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Overleaf Sync — {len(fixtures)} fixture(s)")
    print(f"{sep}\n")

    for fx in fixtures:
        pid = fx["project_id"]
        files = fx["files"]
        yaml_path = fx["case_yaml"]

        existing_id = existing_projects.get(pid)
        action = "EXISTS" if existing_id else "CREATE"

        print(f"  [{action:6}] {pid}  ({len(files)} files)")
        if args.dry_run:
            for f in files:
                print(f"           - {f}")
            continue

        if existing_id:
            if args.include_hidden:
                print(f"    Already on Overleaf (ID: {existing_id}), uploading files (--include-hidden)...")
                try:
                    count = upload_fixture(client, existing_id, fx["fixture_dir"], files)
                    print(f"    Done: {count}/{len(files)} files uploaded.")
                except Exception as e:
                    print(f"    UPLOAD ERROR: {e}")
            else:
                print(f"    Already on Overleaf (ID: {existing_id}), writing to YAML...")
            write_overleaf_id_to_yaml(yaml_path, existing_id)
            continue

        # Create
        print(f"    Creating project...")
        try:
            overleaf_pid = client.create_project(pid)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue
        print(f"    Created (ID: {overleaf_pid})")
        time.sleep(1)

        # Upload
        try:
            count = upload_fixture(client, overleaf_pid, fx["fixture_dir"], files)
            print(f"    Done: {count}/{len(files)} files uploaded.")
        except Exception as e:
            print(f"    UPLOAD ERROR: {e}")

        # Write ID to YAML
        write_overleaf_id_to_yaml(yaml_path, overleaf_pid)
        print(f"    Wrote overleaf_id → {yaml_path.name}")
        time.sleep(0.5)

    print(f"\n{sep}")
    print("  Done.")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
