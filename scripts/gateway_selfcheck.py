#!/usr/bin/env python3
from typing import Optional

import argparse
import json
import shutil
import time
from pathlib import Path
from urllib import error, request


def call_api(base_url: str, method: str, path: str, payload: Optional[dict] = None):
    req = request.Request(base_url + path, method=method)
    if payload is not None:
        req.data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text) if text else None
    except error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            body = json.loads(text)
        except Exception:
            body = {"raw": text}
        return e.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Gateway API 自检（临时项目、自动清理）")
    parser.add_argument("--base-url", default="http://127.0.0.1:18790", help="网关地址，默认 http://127.0.0.1:18790")
    parser.add_argument("--workspace", default="workspace", help="工作区目录（用于临时项目目录创建/清理）")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    workspace = Path(args.workspace)
    pid = f"__selfcheck_{int(time.time())}"
    pdir = workspace / pid
    pdir.mkdir(parents=True, exist_ok=True)

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f" | {detail}" if detail else ""))

    print(f"[INFO] base_url={base_url}")
    print(f"[INFO] temp_project={pid}")

    try:
        c, _ = call_api(base_url, "GET", "/api/projects")
        record("projects_api", c == 200, f"status={c}")

        c, r = call_api(
            base_url,
            "POST",
            f"/api/projects/{pid}/jobs",
            {
                "id": "user.selfcheck.job",
                "name": "Selfcheck Job",
                "type": "normal",
                "schedule": {"cron": "*/30 * * * *", "timezone": "UTC"},
                "prompt": "selfcheck prompt",
                "enabled": True,
            },
        )
        record("create_job", c == 200 and isinstance(r, dict) and r.get("ok") is True, f"status={c}")

        c, r = call_api(
            base_url,
            "PUT",
            f"/api/projects/{pid}/jobs/user.selfcheck.job",
            {
                "name": "Selfcheck Job Updated",
                "type": "task",
                "enabled": False,
                "frozen": True,
                "prompt": "updated prompt",
                "schedule": {"cron": "15 * * * *", "timezone": "UTC"},
            },
        )
        job = r.get("job", {}) if isinstance(r, dict) else {}
        record(
            "update_job_fields",
            c == 200 and job.get("name") == "Selfcheck Job Updated" and job.get("type") == "task" and job.get("enabled") is False,
            f"status={c}",
        )
        record("update_frozen_field", c == 200 and job.get("frozen") is True, f"status={c}, returned_frozen={job.get('frozen')}")

        c, r = call_api(base_url, "GET", f"/api/projects/{pid}/jobs")
        ok_runtime = False
        if c == 200 and isinstance(r, list) and r:
            jj = next((x for x in r if x.get("id") == "user.selfcheck.job"), {})
            rt = jj.get("runtime", {})
            ok_runtime = "run_count" in rt and "total_duration_seconds" in rt
        record("jobs_runtime_fields", ok_runtime, f"status={c}")

        c, r = call_api(base_url, "GET", f"/api/projects/{pid}/runs?limit=20")
        record("runs_api", c == 200 and isinstance(r, list), f"status={c}")

        c, r = call_api(base_url, "POST", f"/api/projects/{pid}/bootstrap?mode=merge")
        record("bootstrap_merge", c == 200 and isinstance(r, dict) and r.get("ok") is True, f"status={c}")

        c, r = call_api(base_url, "POST", f"/api/projects/{pid}/freeze-all-autoplan")
        record("freeze_all_autoplan", c == 200 and isinstance(r, dict) and r.get("ok") is True, f"status={c}")

        c, r = call_api(base_url, "POST", f"/api/projects/{pid}/subscriptions", {"channel": "telegram", "chat_id": "selfcheck-chat"})
        record("subscription_add", c == 200 and isinstance(r, dict) and r.get("ok") is True, f"status={c}")

        c, r = call_api(base_url, "GET", f"/api/projects/{pid}/subscriptions")
        has_sub = c == 200 and isinstance(r, dict) and isinstance(r.get("items"), list)
        record("subscription_list", has_sub, f"status={c}")

        c, r = call_api(base_url, "DELETE", f"/api/projects/{pid}/subscriptions?channel=telegram&chat_id=selfcheck-chat")
        record("subscription_remove", c == 200 and isinstance(r, dict) and r.get("ok") is True, f"status={c}")

        c, r = call_api(base_url, "POST", f"/api/projects/{pid}/jobs/user.selfcheck.job/run")
        record("run_now_api", c in (200, 400, 503), f"status={c}")

        c, r = call_api(base_url, "DELETE", f"/api/projects/{pid}/jobs/user.selfcheck.job")
        record("delete_normal_job", c == 200 and isinstance(r, dict) and r.get("ok") is True, f"status={c}")

        c, _ = call_api(
            base_url,
            "POST",
            f"/api/projects/{pid}/jobs",
            {
                "id": "radar.autoplan",
                "name": "CoreSim",
                "type": "normal",
                "schedule": {"cron": "0 0 * * *", "timezone": "UTC"},
                "prompt": "core protect test",
                "enabled": False,
            },
        )
        c2, r2 = call_api(base_url, "DELETE", f"/api/projects/{pid}/jobs/radar.autoplan")
        record("delete_core_protected", c2 == 403, f"status={c2}, detail={r2}")

    finally:
        shutil.rmtree(pdir, ignore_errors=True)
        print(f"[INFO] cleaned {pdir}")

    failures = [x for x in checks if not x[1]]
    if failures:
        print(f"\n[SUMMARY] FAIL ({len(failures)} items)")
        return 1
    print("\n[SUMMARY] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
