"""Filesystem-based project knowledge and profile store."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ProjectKnowledgeStore:
    """Project-scoped knowledge base with compact index + full entries."""

    def __init__(self, project: Any):
        self.project = project
        self.base_dir = project.root / ".project_memory" / "knowledge"
        self.entries_dir = self.base_dir / "entries"
        self.profiles_dir = self.base_dir / "profiles"
        self.index_json = self.base_dir / "index.json"
        self.index_compact = self.base_dir / "index_compact.md"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def _load_index(self) -> list[dict[str, Any]]:
        if not self.index_json.exists():
            return []
        try:
            data = json.loads(self.index_json.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception as e:
            logger.warning(f"Failed to load knowledge index: {e}")
        return []

    def _save_index(self, records: list[dict[str, Any]]) -> None:
        text = json.dumps(records, ensure_ascii=False, indent=2)
        self._atomic_write(self.index_json, text)

    def _next_memory_id(self) -> str:
        records = self._load_index()
        max_no = 0
        for rec in records:
            mem_id = str(rec.get("id", ""))
            m = re.match(r"MEM-(\d+)$", mem_id)
            if not m:
                continue
            max_no = max(max_no, int(m.group(1)))
        return f"MEM-{max_no + 1:04d}"

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
    ) -> str:
        mem_id = self._next_memory_id()
        entry_name = f"{mem_id}.md"
        entry_path = self.entries_dir / entry_name
        self._atomic_write(entry_path, content)

        summary = content.strip().replace("\n", " ")
        if len(summary) > 180:
            summary = summary[:180] + "..."

        records = self._load_index()
        now = datetime.now().isoformat()
        records.append(
            {
                "id": mem_id,
                "kind": kind,
                "title": title.strip() or mem_id,
                "summary": summary,
                "tags": tags or [],
                "source": source,
                "intent": intent.strip(),
                "scope": scope.strip(),
                "path": str(entry_path.relative_to(self.base_dir)),
                "updated_at": now,
            }
        )
        self._save_index(records)
        self.refresh_compact_index()
        return mem_id

    def get_entry(self, memory_id: str) -> dict[str, Any] | None:
        records = self._load_index()
        record = next((r for r in records if str(r.get("id")) == memory_id), None)
        if not record:
            return None
        rel = record.get("path", "")
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

    def search_entries(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return []
        scored: list[tuple[int, dict[str, Any]]] = []
        for rec in self._load_index():
            text = " ".join(
                [
                    str(rec.get("title", "")),
                    str(rec.get("summary", "")),
                    " ".join(rec.get("tags", [])) if isinstance(rec.get("tags"), list) else "",
                    str(rec.get("intent", "")),
                    str(rec.get("scope", "")),
                ]
            ).lower()
            score = text.count(q)
            if score <= 0:
                continue
            scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[: max(top_k, 1)]]

    @staticmethod
    def _scope_domain(scope: str) -> str:
        raw = (scope or "").strip()
        if not raw:
            return "project"
        if ":" in raw:
            return raw.split(":", 1)[0].strip() or "project"
        return raw

    def list_scopes(self, domain: str = "all", intent: str = "", limit: int = 30) -> list[dict[str, Any]]:
        """
        Hierarchical navigation layer:
        summarize memory scopes for LLM to choose where to drill down.
        """
        want_domain = (domain or "all").strip().lower()
        want_intent = (intent or "").strip().lower()
        buckets: dict[str, dict[str, Any]] = {}

        for rec in self._load_index():
            scope = str(rec.get("scope", "")).strip() or "project"
            rec_intent = str(rec.get("intent", "")).strip()
            rec_domain = self._scope_domain(scope).lower()
            if want_domain != "all" and rec_domain != want_domain:
                continue
            if want_intent and rec_intent.lower() != want_intent:
                continue

            bucket = buckets.get(scope)
            if not bucket:
                bucket = {
                    "scope": scope,
                    "domain": rec_domain,
                    "count": 0,
                    "last_updated": "",
                    "latest_id": "",
                    "latest_title": "",
                    "intents": set(),
                }
                buckets[scope] = bucket

            bucket["count"] += 1
            if rec_intent:
                bucket["intents"].add(rec_intent)
            updated = str(rec.get("updated_at", "")).strip()
            if updated >= str(bucket.get("last_updated", "")):
                bucket["last_updated"] = updated
                bucket["latest_id"] = str(rec.get("id", "")).strip()
                bucket["latest_title"] = str(rec.get("title", "")).strip()

        rows: list[dict[str, Any]] = []
        for item in buckets.values():
            intents = sorted(i for i in item.get("intents", set()) if i)
            rows.append(
                {
                    "scope": item["scope"],
                    "domain": item["domain"],
                    "count": item["count"],
                    "last_updated": item["last_updated"],
                    "latest_id": item["latest_id"],
                    "latest_title": item["latest_title"],
                    "intents": intents[:6],
                }
            )
        rows.sort(key=lambda x: (str(x.get("last_updated", "")), int(x.get("count", 0))), reverse=True)
        return rows[: max(limit, 1)]

    def list_entries_by_scope(
        self,
        scope: str,
        *,
        intent: str = "",
        since: str = "",
        limit: int = 20,
        cursor: str = "",
    ) -> dict[str, Any]:
        """
        List memory entries under one scope with simple offset pagination.
        cursor format: numeric offset string (e.g. "0", "20").
        """
        normalized_scope = str(scope or "").strip() or "project"
        want_intent = (intent or "").strip().lower()
        since_mark = str(since or "").strip()

        records: list[dict[str, Any]] = []
        for rec in self._load_index():
            rec_scope = str(rec.get("scope", "")).strip() or "project"
            if rec_scope != normalized_scope:
                continue
            rec_intent = str(rec.get("intent", "")).strip()
            if want_intent and rec_intent.lower() != want_intent:
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
                    "updated_at": str(rec.get("updated_at", "")),
                    "tags": rec.get("tags", []) if isinstance(rec.get("tags"), list) else [],
                }
            )

        return {
            "scope": normalized_scope,
            "intent": want_intent,
            "since": since_mark,
            "total": len(records),
            "count": len(items),
            "next_cursor": next_cursor,
            "items": items,
        }

    def refresh_compact_index(self, limit: int = 30) -> str:
        records = sorted(
            self._load_index(),
            key=lambda x: str(x.get("updated_at", "")),
            reverse=True,
        )
        lines = []
        for rec in records[: max(limit, 1)]:
            mem_id = rec.get("id", "MEM-????")
            title = str(rec.get("title", "")).strip()
            summary = str(rec.get("summary", "")).strip()
            lines.append(f"- [{mem_id}] {title}: {summary}")
        text = "\n".join(lines).strip()
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

    def read_profile(self, name: str) -> dict[str, Any]:
        target = self.profiles_dir / f"{name}.current.json"
        if not target.exists():
            return {}
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def write_profile(self, name: str, payload: dict[str, Any]) -> None:
        target = self.profiles_dir / f"{name}.current.json"
        payload = dict(payload)
        payload["updated_at"] = datetime.now().isoformat()
        self._atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2))

    def append_profile_history(self, name: str, payload: dict[str, Any]) -> None:
        target = self.profiles_dir / f"{name}.history.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def read_profile_history(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        target = self.profiles_dir / f"{name}.history.jsonl"
        if not target.exists():
            return []
        items: list[dict[str, Any]] = []
        try:
            for line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    items.append(payload)
        except Exception as e:
            logger.debug(f"Failed to read profile history ({name}): {e}")
            return []
        items = sorted(items, key=lambda x: str(x.get("updated_at", "")), reverse=True)
        return items[: max(limit, 1)]

    def summarize_research_trajectory(self, limit: int = 6) -> str:
        """
        Build a compact natural-language trajectory from research_core history.
        Keeps only distinct consecutive snapshots to avoid repetitive noise.
        """
        history = self.read_profile_history("research_core", limit=max(limit * 4, 8))
        if not history:
            return ""

        lines: list[str] = []
        last_sig: tuple[str, str, tuple[str, ...]] | None = None
        for row in history:
            topic = str(row.get("topic", "")).strip()
            stage = str(row.get("stage", "")).strip()
            keywords = row.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            kw = [str(x).strip() for x in keywords if str(x).strip()][:4]
            sig = (topic, stage, tuple(kw))
            if sig == last_sig:
                continue
            last_sig = sig

            stamp = str(row.get("updated_at", "")).strip()
            stamp = stamp[:16] if stamp else "unknown_time"
            kw_text = ", ".join(kw) if kw else "-"
            lines.append(f"- {stamp}: topic={topic or '-'}; stage={stage or '-'}; keywords={kw_text}")
            if len(lines) >= max(limit, 1):
                break
        return "\n".join(lines)

    def render_system_memory_brief(self, index_limit: int = 12) -> str:
        """
        Render concise, auto-loaded memory background for system prompts.
        Full details should be resolved later via memory_get/memory_search.
        """
        research = self.read_profile("research_core")
        pref = self.read_profile("user_preference")
        trajectory = self.summarize_research_trajectory(limit=5)
        compact = self.read_compact_index(limit=max(index_limit, 1))

        lines: list[str] = []
        if research:
            topic = research.get("topic", "")
            stage = research.get("stage", "")
            keywords = research.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            kw = ", ".join(str(k) for k in keywords[:8] if str(k).strip())
            lines.append("Project Snapshot:")
            lines.append(f"- topic: {topic or '-'}")
            lines.append(f"- stage: {stage or '-'}")
            lines.append(f"- keywords: {kw or '-'}")

        if pref:
            prefs = pref.get("preferences", {}) if isinstance(pref.get("preferences"), dict) else {}
            push_style = str(prefs.get("push_style", "")).strip()
            language = str(prefs.get("language", "")).strip()
            focus = prefs.get("focus", [])
            if not isinstance(focus, list):
                focus = []
            lines.append("User Preference Snapshot:")
            lines.append(f"- push_style: {push_style or '-'}")
            lines.append(f"- language: {language or '-'}")
            lines.append(f"- focus: {', '.join(str(x) for x in focus if str(x).strip()) or '-'}")

        if trajectory:
            lines.append("Research Direction Trajectory (recent):")
            lines.append(trajectory)

        if compact:
            lines.append("Memory Index (fetch full content via memory_get by ID):")
            lines.append(compact)

        return "\n".join(lines).strip()

    def refresh_default_profiles(self) -> dict[str, Any]:
        """Rebuild core project profiles from project files and interaction logs."""
        research_core = self._build_research_core_profile()
        user_pref = self._build_user_preference_profile()

        self.write_profile("research_core", research_core)
        self.append_profile_history("research_core", research_core)
        self.write_profile("user_preference", user_pref)
        self.append_profile_history("user_preference", user_pref)

        return {"research_core": research_core, "user_preference": user_pref}

    def _build_research_core_profile(self) -> dict[str, Any]:
        core = self.project.core
        tex_files = sorted(core.glob("*.tex"))
        corpus = []
        for tex in tex_files[:10]:
            try:
                text = tex.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # Rough cleanup for latex commands.
            text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", text)
            text = re.sub(r"[%].*$", " ", text, flags=re.MULTILINE)
            corpus.append(text[:3000])

        joined = "\n".join(corpus)
        words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{3,}", joined.lower())
        stop = {
            "this",
            "that",
            "with",
            "from",
            "using",
            "paper",
            "method",
            "results",
            "table",
            "figure",
            "section",
            "approach",
            "model",
            "models",
            "data",
            "experiments",
            "introduction",
            "related",
            "work",
            "conclusion",
        }
        keywords = [w for w, _ in Counter(w for w in words if w not in stop).most_common(15)]
        stage = "writing"
        if "deadline" in joined.lower() or "submission" in joined.lower():
            stage = "submission"
        elif "experiment" in joined.lower():
            stage = "experiment"

        topic = self.project.id.replace("_", " ")
        if keywords:
            topic = f"{keywords[0]} / {keywords[1]}" if len(keywords) > 1 else keywords[0]

        return {
            "project_id": self.project.id,
            "topic": topic,
            "keywords": keywords,
            "stage": stage,
            "source_files": [f.name for f in tex_files[:10]],
        }

    def _build_user_preference_profile(self) -> dict[str, Any]:
        project_root = self.project.root
        sessions = [d for d in project_root.iterdir() if d.is_dir() and d.name != self.project.id and not d.name.startswith(".")]
        sessions = sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)[:8]

        text_buf: list[str] = []
        for session_dir in sessions:
            history_dir = session_dir / ".bot" / "memory" / "history"
            if not history_dir.exists():
                continue
            for log_file in sorted(history_dir.glob("chat_*.jsonl"), reverse=True)[:2]:
                try:
                    for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]:
                        try:
                            entry = json.loads(line)
                        except Exception:
                            continue
                        if entry.get("type") != "inbound":
                            continue
                        content = str(entry.get("content", "")).strip()
                        if content:
                            text_buf.append(content)
                except Exception:
                    continue

        joined = "\n".join(text_buf).lower()
        prefs = {
            "push_style": "important_only",
            "focus": [],
            "language": "zh",
        }
        if "daily" in joined or "日报" in joined:
            prefs["push_style"] = "daily_digest"
        if "urgent" in joined or "紧急" in joined:
            prefs["focus"].append("urgent_alerts")
        if "deadline" in joined or "截稿" in joined:
            prefs["focus"].append("deadlines")
        if "novelty" in joined or "创新" in joined:
            prefs["focus"].append("novelty")
        if "english" in joined:
            prefs["language"] = "en"

        return {
            "project_id": self.project.id,
            "preferences": prefs,
            "sampled_messages": len(text_buf),
        }
