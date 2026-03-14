"""Unified project memory store for automation/autoplan chains."""

from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from core.memory.builders import TexResearchProfileBuilder
from core.memory.profile_builder import ProfileBuilder
from core.profile.fs_memory import ProjectKnowledgeStore

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None

_TTL_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)


class ProjectMemoryStore(ProjectKnowledgeStore):
    """Filesystem-backed unified memory store for automation and autoplan."""

    _thread_locks: dict[str, threading.Lock] = {}
    _thread_locks_guard = threading.Lock()
    _GC_INTERVAL_HOURS = 24

    def __init__(self, project: Any):
        # Keep parent initialization to preserve inherited helpers, then switch paths.
        super().__init__(project)
        self.base_dir = project.root / ".project_memory"
        self.entries_dir = self.base_dir / "entries"
        self.profiles_dir = self.base_dir / "profiles"
        self.index_json = self.base_dir / "index.jsonl"  # JSONL format (one record per line)
        self.index_compact = self.base_dir / "index_compact.md"
        self.migrations_dir = self.base_dir / ".migrations"
        ProjectKnowledgeStore._ensure_dirs(self)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_index_to_jsonl()

    # ------------------------------------------------------------------
    # JSONL index (overrides parent's JSON array implementation)
    # ------------------------------------------------------------------

    def _load_index(self) -> list[dict[str, Any]]:
        """Load index from JSONL — one JSON object per line, skip blanks/bad lines."""
        if not self.index_json.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            for line in self.index_json.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        records.append(obj)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to load memory index: {e}")
        return records

    def _save_index(self, records: list[dict[str, Any]]) -> None:
        """Write index as JSONL — compact, one record per line, grep-friendly."""
        text = "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records)
        self._atomic_write(self.index_json, text + "\n" if text else "")

    def _migrate_index_to_jsonl(self) -> None:
        """One-time migration: if index.json exists and index.jsonl doesn't, convert."""
        old = self.base_dir / "index.json"
        if not old.exists() or self.index_json.exists():
            return
        try:
            data = json.loads(old.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            records = [r for r in data if isinstance(r, dict)]
            self._save_index(records)
            old.rename(old.with_suffix(".json.migrated"))
            logger.info(f"Migrated index.json → index.jsonl ({len(records)} entries)")
        except Exception as e:
            logger.warning(f"index.json → index.jsonl migration failed: {e}")

    # ------------------------------------------------------------------
    # Auto GC (lazy, triggered after writes)
    # ------------------------------------------------------------------

    def _maybe_gc(self) -> None:
        """Run GC if the last-gc marker is older than _GC_INTERVAL_HOURS."""
        marker = self.base_dir / ".last_gc"
        try:
            if marker.exists():
                ts = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
                if (datetime.now() - ts).total_seconds() < self._GC_INTERVAL_HOURS * 3600:
                    return
            n = self.gc()
            marker.write_text(datetime.now().isoformat(), encoding="utf-8")
            if n:
                logger.debug(f"Auto-GC: removed {n} expired entries")
        except Exception as e:
            logger.debug(f"Auto-GC skipped: {e}")

    # ------------------------------------------------------------------
    # Locking helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _file_lock(self, name: str = "index.lock"):
        lock_path = self.base_dir / name
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_key = str(lock_path.resolve())

        with self._thread_locks_guard:
            thread_lock = self._thread_locks.setdefault(lock_key, threading.Lock())

        with thread_lock:
            fh = None
            try:
                fh = open(lock_path, "a+", encoding="utf-8")
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                if fh is not None:
                    if fcntl is not None:
                        try:
                            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                        except Exception:
                            pass
                    fh.close()

    @staticmethod
    def _next_memory_id_from_records(records: list[dict[str, Any]]) -> str:
        max_no = 0
        for rec in records:
            mem_id = str(rec.get("id", "")).strip()
            m = re.match(r"MEM-(\d+)$", mem_id)
            if not m:
                continue
            max_no = max(max_no, int(m.group(1)))
        return f"MEM-{max_no + 1:04d}"

    # ------------------------------------------------------------------
    # Entry CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize(text: str, limit: int = 180) -> str:
        out = (text or "").strip().replace("\n", " ")
        if len(out) <= limit:
            return out
        return out[:limit] + "..."

    def add(
        self,
        *,
        kind: str = "note",
        scope: str = "project",
        intent: str = "",
        title: str,
        content: str,
        tags: list[str] | None = None,
        source: str = "agent",
        ttl: str | None = None,
        parent_id: str | None = None,
        created_at: str | None = None,
    ) -> str:
        body = str(content or "")
        normalized_tags = sorted({str(t).strip() for t in (tags or []) if str(t).strip()})
        now = datetime.now().isoformat()
        created = str(created_at).strip() if str(created_at or "").strip() else now
        normalized_scope = str(scope or "").strip() or "project"

        with self._file_lock("index.lock"):
            records = self._load_index()
            mem_id = self._next_memory_id_from_records(records)
            entry_path = self.entries_dir / f"{mem_id}.md"
            self._atomic_write(entry_path, body)

            records.append(
                {
                    "id": mem_id,
                    "kind": str(kind or "note"),
                    "scope": normalized_scope,
                    "intent": str(intent or "").strip(),
                    "title": str(title or "").strip() or mem_id,
                    "summary": self._summarize(body),
                    "tags": normalized_tags,
                    "source": str(source or "agent").strip() or "agent",
                    "created_at": created,
                    "updated_at": now,
                    "ttl": str(ttl).strip() if ttl is not None and str(ttl).strip() else None,
                    "parent_id": str(parent_id).strip() if parent_id is not None and str(parent_id).strip() else None,
                    "path": str(entry_path.relative_to(self.base_dir)),
                }
            )
            self._save_index(records)

        self.refresh_compact_index()
        self._maybe_gc()
        return mem_id

    def add_entry(
        self,
        *,
        title: str,
        content: str,
        tags: list[str] | None = None,
        source: str = "manual",
        kind: str = "note",
        intent: str = "",
        scope: str = "",
        ttl: str | None = None,
        parent_id: str | None = None,
        created_at: str | None = None,
    ) -> str:
        return self.add(
            kind=kind,
            scope=scope,
            intent=intent,
            title=title,
            content=content,
            tags=tags,
            source=source,
            ttl=ttl,
            parent_id=parent_id,
            created_at=created_at,
        )

    def get(self, memory_id: str) -> dict[str, Any] | None:
        memory_id = str(memory_id or "").strip()
        if not memory_id:
            return None
        record = next((r for r in self._load_index() if str(r.get("id")) == memory_id), None)
        if not record:
            return None
        rel = str(record.get("path", "")).strip()
        if not rel:
            return None
        path = self.base_dir / rel
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None
        out = dict(record)
        out["content"] = content
        return out

    def get_entry(self, memory_id: str) -> dict[str, Any] | None:
        return self.get(memory_id)

    def update(self, memory_id: str, patch: dict[str, Any]) -> bool:
        if not isinstance(patch, dict):
            return False
        memory_id = str(memory_id or "").strip()
        if not memory_id:
            return False

        updated = False
        with self._file_lock("index.lock"):
            records = self._load_index()
            for rec in records:
                if str(rec.get("id", "")).strip() != memory_id:
                    continue

                content = patch.get("content")
                if content is not None:
                    rel = str(rec.get("path", "")).strip()
                    if rel:
                        self._atomic_write(self.base_dir / rel, str(content))
                        rec["summary"] = self._summarize(str(content))

                for key in ("kind", "scope", "intent", "title", "tags", "source", "ttl", "parent_id"):
                    if key in patch:
                        rec[key] = patch[key]
                rec["updated_at"] = datetime.now().isoformat()
                updated = True
                break

            if updated:
                self._save_index(records)

        if updated:
            self.refresh_compact_index()
        return updated

    def delete(self, memory_id: str) -> bool:
        memory_id = str(memory_id or "").strip()
        if not memory_id:
            return False

        removed = False
        with self._file_lock("index.lock"):
            records = self._load_index()
            kept: list[dict[str, Any]] = []
            target: dict[str, Any] | None = None
            for rec in records:
                if str(rec.get("id", "")).strip() == memory_id and target is None:
                    target = rec
                    continue
                kept.append(rec)

            if target is not None:
                rel = str(target.get("path", "")).strip()
                if rel:
                    try:
                        (self.base_dir / rel).unlink(missing_ok=True)
                    except Exception:
                        pass
                self._save_index(kept)
                removed = True

        if removed:
            self.refresh_compact_index()
        return removed

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    @staticmethod
    def _scope_matches(scope: str, want_scope: str) -> bool:
        raw = str(want_scope or "").strip()
        if not raw:
            return True
        if raw.endswith("*"):
            return scope.startswith(raw[:-1])
        return scope == raw

    def nav(self, domain: str = "all", intent: str = "", kind: str = "", limit: int = 30) -> list[dict[str, Any]]:
        want_domain = (domain or "all").strip().lower()
        want_intent = (intent or "").strip().lower()
        want_kind = (kind or "").strip().lower()
        buckets: dict[str, dict[str, Any]] = {}

        for rec in self._load_index():
            rec_scope = str(rec.get("scope", "")).strip() or "project"
            rec_domain = self._scope_domain(rec_scope).lower()
            rec_intent = str(rec.get("intent", "")).strip().lower()
            rec_kind = str(rec.get("kind", "")).strip().lower()

            if want_domain != "all" and rec_domain != want_domain:
                continue
            if want_intent and rec_intent != want_intent:
                continue
            if want_kind and rec_kind != want_kind:
                continue

            bucket = buckets.get(rec_scope)
            if not bucket:
                bucket = {
                    "scope": rec_scope,
                    "domain": rec_domain,
                    "count": 0,
                    "last_updated": "",
                    "latest_id": "",
                    "latest_title": "",
                    "intents": set(),
                    "kinds": set(),
                }
                buckets[rec_scope] = bucket

            bucket["count"] += 1
            if rec_intent:
                bucket["intents"].add(rec_intent)
            if rec_kind:
                bucket["kinds"].add(rec_kind)
            updated = str(rec.get("updated_at", "")).strip()
            if updated >= str(bucket.get("last_updated", "")):
                bucket["last_updated"] = updated
                bucket["latest_id"] = str(rec.get("id", "")).strip()
                bucket["latest_title"] = str(rec.get("title", "")).strip()

        rows: list[dict[str, Any]] = []
        for bucket in buckets.values():
            rows.append(
                {
                    "scope": bucket["scope"],
                    "domain": bucket["domain"],
                    "count": bucket["count"],
                    "last_updated": bucket["last_updated"],
                    "latest_id": bucket["latest_id"],
                    "latest_title": bucket["latest_title"],
                    "intents": sorted(bucket["intents"])[:6],
                    "kinds": sorted(bucket["kinds"])[:6],
                }
            )

        rows.sort(key=lambda x: (str(x.get("last_updated", "")), int(x.get("count", 0))), reverse=True)
        return rows[: max(limit, 1)]

    def list_scopes(self, domain: str = "all", intent: str = "", limit: int = 30, kind: str = "") -> list[dict[str, Any]]:
        return self.nav(domain=domain, intent=intent, kind=kind, limit=limit)

    def list_by_scope(
        self,
        scope: str,
        *,
        intent: str = "",
        kind: str = "",
        since: str = "",
        limit: int = 20,
        cursor: str = "",
    ) -> dict[str, Any]:
        normalized_scope = str(scope or "").strip() or "project"
        want_intent = (intent or "").strip().lower()
        want_kind = (kind or "").strip().lower()
        since_mark = str(since or "").strip()

        records: list[dict[str, Any]] = []
        for rec in self._load_index():
            rec_scope = str(rec.get("scope", "")).strip() or "project"
            if not self._scope_matches(rec_scope, normalized_scope):
                continue

            rec_intent = str(rec.get("intent", "")).strip().lower()
            if want_intent and rec_intent != want_intent:
                continue

            rec_kind = str(rec.get("kind", "")).strip().lower()
            if want_kind and rec_kind != want_kind:
                continue

            updated = str(rec.get("updated_at", "")).strip()
            if since_mark and updated and updated < since_mark:
                continue

            records.append(rec)

        records.sort(key=lambda x: (str(x.get("updated_at", "")), str(x.get("id", ""))), reverse=True)

        try:
            offset = max(int(str(cursor or "0")), 0)
        except Exception:
            offset = 0

        max_limit = max(min(int(limit), 100), 1)
        page = records[offset : offset + max_limit]
        next_cursor = str(offset + max_limit) if (offset + max_limit) < len(records) else ""

        items: list[dict[str, Any]] = []
        for rec in page:
            items.append(
                {
                    "id": str(rec.get("id", "")),
                    "title": str(rec.get("title", "")),
                    "summary": str(rec.get("summary", "")),
                    "kind": str(rec.get("kind", "")),
                    "intent": str(rec.get("intent", "")),
                    "scope": str(rec.get("scope", "")) or "project",
                    "source": str(rec.get("source", "")),
                    "created_at": str(rec.get("created_at", "")),
                    "updated_at": str(rec.get("updated_at", "")),
                    "ttl": rec.get("ttl"),
                    "parent_id": rec.get("parent_id"),
                    "tags": rec.get("tags", []) if isinstance(rec.get("tags"), list) else [],
                }
            )

        return {
            "scope": normalized_scope,
            "intent": want_intent,
            "kind": want_kind,
            "since": since_mark,
            "total": len(records),
            "count": len(items),
            "next_cursor": next_cursor,
            "items": items,
        }

    def list_entries_by_scope(
        self,
        scope: str,
        *,
        intent: str = "",
        since: str = "",
        limit: int = 20,
        cursor: str = "",
        kind: str = "",
    ) -> dict[str, Any]:
        return self.list_by_scope(
            scope,
            intent=intent,
            kind=kind,
            since=since,
            limit=limit,
            cursor=cursor,
        )

    def list_recent_entries(self, *, kind: str = "", scope_prefix: str = "", limit: int = 20) -> list[dict[str, Any]]:
        records = sorted(self._load_index(), key=lambda x: str(x.get("updated_at", "")), reverse=True)
        out: list[dict[str, Any]] = []
        want_kind = str(kind or "").strip().lower()
        prefix = str(scope_prefix or "").strip()

        for rec in records:
            rec_kind = str(rec.get("kind", "")).strip().lower()
            if want_kind and rec_kind != want_kind:
                continue
            rec_scope = str(rec.get("scope", "")).strip()
            if prefix and not rec_scope.startswith(prefix):
                continue
            out.append(
                {
                    "id": str(rec.get("id", "")),
                    "title": str(rec.get("title", "")),
                    "summary": str(rec.get("summary", "")),
                    "kind": str(rec.get("kind", "")),
                    "intent": str(rec.get("intent", "")),
                    "scope": rec_scope,
                    "source": str(rec.get("source", "")),
                    "created_at": str(rec.get("created_at", "")),
                    "updated_at": str(rec.get("updated_at", "")),
                    "tags": rec.get("tags", []) if isinstance(rec.get("tags"), list) else [],
                }
            )
            if len(out) >= max(limit, 1):
                break
        return out

    def search(self, query: str, *, kind: str = "", scope: str = "", top_k: int = 5) -> list[dict[str, Any]]:
        q = str(query or "").strip().lower()
        want_kind = str(kind or "").strip().lower()
        want_scope = str(scope or "").strip()

        if not q:
            return self.list_recent_entries(kind=want_kind, scope_prefix=want_scope, limit=top_k)

        scored: list[tuple[int, str, dict[str, Any]]] = []
        for rec in self._load_index():
            rec_kind = str(rec.get("kind", "")).strip().lower()
            if want_kind and rec_kind != want_kind:
                continue

            rec_scope = str(rec.get("scope", "")).strip()
            if want_scope and not self._scope_matches(rec_scope, want_scope):
                continue

            text = " ".join(
                [
                    str(rec.get("title", "")),
                    str(rec.get("summary", "")),
                    " ".join(rec.get("tags", [])) if isinstance(rec.get("tags"), list) else "",
                    str(rec.get("intent", "")),
                    rec_scope,
                ]
            ).lower()
            score = text.count(q)
            if score <= 0:
                continue
            scored.append((score, str(rec.get("updated_at", "")), rec))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [item for _, _, item in scored[: max(top_k, 1)]]

    def search_entries(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.search(query, top_k=top_k)

    # ------------------------------------------------------------------
    # Compact index
    # ------------------------------------------------------------------

    def compact_index(self, limit: int = 30, kind_filter: str = "") -> str:
        want_kind = str(kind_filter or "").strip().lower()
        records = sorted(self._load_index(), key=lambda x: str(x.get("updated_at", "")), reverse=True)
        lines: list[str] = []

        for rec in records:
            rec_kind = str(rec.get("kind", "")).strip().lower()
            if want_kind and rec_kind != want_kind:
                continue
            mem_id = rec.get("id", "MEM-????")
            title = str(rec.get("title", "")).strip()
            summary = str(rec.get("summary", "")).strip()
            lines.append(f"- [{mem_id}] {title}: {summary}")
            if len(lines) >= max(limit, 1):
                break

        return "\n".join(lines).strip()

    def refresh_compact_index(self, limit: int = 30) -> str:
        text = self.compact_index(limit=limit)
        self._atomic_write(self.index_compact, text + ("\n" if text else ""))
        return text

    def read_compact_index(self, limit: int = 30) -> str:
        if not self.index_compact.exists():
            return self.refresh_compact_index(limit=limit)
        try:
            raw = self.index_compact.read_text(encoding="utf-8")
            lines = [ln for ln in raw.splitlines() if ln.strip()]
            return "\n".join(lines[: max(limit, 1)])
        except Exception:
            return self.refresh_compact_index(limit=limit)

    # ------------------------------------------------------------------
    # Profile APIs
    # ------------------------------------------------------------------

    @staticmethod
    def _default_builders(provider: Any = None, model: str | None = None) -> list[ProfileBuilder]:
        return [TexResearchProfileBuilder(provider=provider, model=model)]

    def refresh_profiles(
        self,
        builders: list[ProfileBuilder] | None = None,
        provider: Any = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        selected = builders or self._default_builders(provider=provider, model=model)
        results: dict[str, Any] = {}
        for builder in selected:
            name = str(getattr(builder, "name", "")).strip()
            if not name:
                continue
            try:
                payload = builder.build(self.project)
                if not isinstance(payload, dict):
                    logger.warning(f"Profile builder {name} returned non-dict payload")
                    continue
                self.write_profile(name, payload)
                self.append_profile_history(name, payload)
                results[name] = payload
            except Exception as e:
                logger.warning(f"Profile builder {name} failed: {e}")
        return results

    def refresh_default_profiles(self, provider: Any = None, model: str | None = None) -> dict[str, Any]:
        return self.refresh_profiles(provider=provider, model=model)

    # ------------------------------------------------------------------
    # Lifecycle / migration
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ttl(ttl: str | None) -> timedelta | None:
        raw = str(ttl or "").strip()
        if not raw:
            return None
        m = _TTL_RE.match(raw)
        if not m:
            return None
        value = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "s":
            return timedelta(seconds=value)
        if unit == "m":
            return timedelta(minutes=value)
        if unit == "h":
            return timedelta(hours=value)
        if unit == "d":
            return timedelta(days=value)
        if unit == "w":
            return timedelta(weeks=value)
        return None

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    def _collect_job_state_refs(self) -> set[str]:
        refs: set[str] = set()
        states_dir = self.base_dir / "job_states"
        if not states_dir.exists():
            return refs

        for path in states_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            mem_id = str(payload.get("last_entry_id", "")).strip()
            if mem_id:
                refs.add(mem_id)
        return refs

    def gc(self, now: datetime | None = None, *, protect_job_state_refs: bool = True) -> int:
        now_dt = now or datetime.now()
        protected = self._collect_job_state_refs() if protect_job_state_refs else set()

        removed_records: list[dict[str, Any]] = []
        with self._file_lock("index.lock"):
            records = self._load_index()
            kept: list[dict[str, Any]] = []

            for rec in records:
                mem_id = str(rec.get("id", "")).strip()
                ttl_delta = self._parse_ttl(rec.get("ttl"))
                if ttl_delta is None:
                    kept.append(rec)
                    continue

                if mem_id and mem_id in protected:
                    kept.append(rec)
                    continue

                anchor = self._parse_time(rec.get("created_at")) or self._parse_time(rec.get("updated_at"))
                if anchor is None:
                    kept.append(rec)
                    continue

                if anchor + ttl_delta > now_dt:
                    kept.append(rec)
                    continue

                removed_records.append(rec)

            if removed_records:
                self._save_index(kept)
                for rec in removed_records:
                    rel = str(rec.get("path", "")).strip()
                    if not rel:
                        continue
                    try:
                        (self.base_dir / rel).unlink(missing_ok=True)
                    except Exception as e:
                        logger.debug(f"Failed to remove expired entry file {rel}: {e}")

        if removed_records:
            self.refresh_compact_index()
        return len(removed_records)

    def migrate_runs_from_legacy(self, *, limit: int = 100000) -> dict[str, Any]:
        marker = self.migrations_dir / "runs_to_entries.v1.done"
        if marker.exists():
            return {"migrated": 0, "skipped": "already_done"}

        legacy_runs_dir = self.project.root / ".project_memory" / "automation" / "runs"
        if not legacy_runs_dir.exists():
            marker.write_text(datetime.now().isoformat(), encoding="utf-8")
            return {"migrated": 0, "skipped": "legacy_runs_missing"}

        existing_run_tags: set[str] = set()
        for rec in self._load_index():
            tags = rec.get("tags", [])
            if not isinstance(tags, list):
                continue
            for tag in tags:
                raw = str(tag).strip()
                if raw.startswith("run:"):
                    existing_run_tags.add(raw)

        migrated = 0
        for path in sorted(legacy_runs_dir.glob("*.json"))[: max(limit, 1)]:
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(run, dict):
                continue

            job_id = str(run.get("job_id", "")).strip()
            if not job_id:
                continue

            run_id = str(run.get("run_id", "")).strip()
            run_tag = f"run:{run_id}" if run_id else ""
            if run_tag and run_tag in existing_run_tags:
                continue

            stamp = str(run.get("ended_at") or run.get("started_at") or datetime.now().isoformat())
            status = str(run.get("status") or "unknown")
            summary = str(run.get("output_excerpt") or "").strip()
            error = str(run.get("error") or "").strip()
            lines = [
                f"Job: {job_id}",
                f"Run ID: {run_id or '-'}",
                f"Started: {run.get('started_at')}",
                f"Ended: {run.get('ended_at')}",
                f"Status: {status}",
                "",
            ]
            if summary:
                lines.extend(["Run Summary:", summary[:3000], ""])
            if error:
                lines.extend(["Run Error:", error[:1200]])

            tags = ["automation", f"job:{job_id}", f"status:{status}"]
            if run_tag:
                tags.append(run_tag)

            self.add(
                kind="job_run",
                scope=f"job:{job_id}",
                intent="job_progress",
                title=f"{job_id} run @ {stamp[:16]}",
                content="\n".join(lines).strip(),
                tags=tags,
                source="migration:runs_to_entries",
                ttl="30d",
                created_at=str(run.get("started_at") or run.get("ended_at") or "").strip() or None,
            )
            migrated += 1
            if run_tag:
                existing_run_tags.add(run_tag)

        marker.write_text(datetime.now().isoformat(), encoding="utf-8")
        return {"migrated": migrated}
