"""Project knowledge and profile tools (filesystem-backed)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.tools.base import BaseTool
from core.memory import ProjectMemoryStore
from core.profile import ProjectKnowledgeStore


class _KnowledgeTool(BaseTool):
    """Shared base for knowledge/profile tools."""

    def __init__(self, project: Any = None, tool_context: Any = None, **kwargs):
        self.project = project
        self.tool_context = tool_context

    def _is_automation_context(self) -> bool:
        if not self.tool_context:
            return False
        session = getattr(self.tool_context, "session", None)
        session_id = str(getattr(session, "id", "") or "").strip().lower()
        return session_id == "automation"

    def _store(self) -> Any | None:
        if not self.project:
            return None
        if self._is_automation_context():
            return ProjectMemoryStore(self.project)
        return ProjectKnowledgeStore(self.project)


class MemoryGetTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "memory_get"

    @property
    def description(self) -> str:
        return "Read full memory content by ID (e.g., MEM-0001)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Memory entry ID, e.g. MEM-0001."}},
            "required": ["id"],
        }

    def execute(self, id: str, **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        item = store.get(id) if hasattr(store, "get") else store.get_entry(id)
        if not item:
            return f"[ERROR] memory entry not found: {id}"
        return (
            f"ID: {item.get('id')}\n"
            f"Kind: {item.get('kind', '')}\n"
            f"Intent: {item.get('intent', '')}\n"
            f"Scope: {item.get('scope', '')}\n"
            f"Title: {item.get('title', '')}\n"
            f"Tags: {', '.join(item.get('tags', [])) if isinstance(item.get('tags'), list) else ''}\n"
            f"Source: {item.get('source', '')}\n\n"
            f"{item.get('content', '')}"
        )


class MemoryNavTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "memory_nav"

    @property
    def description(self) -> str:
        return "List memory scopes (hierarchical navigation layer) by domain/intent."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Scope domain filter: all|job|project|user (or custom prefix).",
                    "default": "all",
                },
                "intent": {
                    "type": "string",
                    "description": "Optional intent filter.",
                    "default": "",
                },
                "kind": {
                    "type": "string",
                    "description": "Optional kind filter (e.g. job_run/note/insight/fact).",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of scopes.",
                    "default": 30,
                },
            },
        }

    def execute(self, domain: str = "all", intent: str = "", kind: str = "", limit: int = 30, **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        if hasattr(store, "nav"):
            rows = store.nav(domain=domain, intent=intent, kind=kind, limit=limit)
        else:
            rows = store.list_scopes(domain=domain, intent=intent, limit=limit)
        if not rows:
            return "No memory scopes found."
        lines = [f"Memory Scopes (domain={domain}, intent={intent or 'all'}, kind={kind or 'all'}):"]
        for row in rows:
            lines.append(
                f"- scope={row.get('scope', '')} | domain={row.get('domain', '')} | count={row.get('count', 0)} | "
                f"last={row.get('last_updated', '')} | latest=[{row.get('latest_id', '')}] {row.get('latest_title', '')}"
            )
        return "\n".join(lines)


class MemoryListTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "memory_list"

    @property
    def description(self) -> str:
        return "List memory cards under one scope with pagination (for layered drill-down)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "description": "Target scope, e.g. job:radar.daily.scan or project."},
                "intent": {"type": "string", "description": "Optional intent filter.", "default": ""},
                "kind": {"type": "string", "description": "Optional kind filter.", "default": ""},
                "since": {"type": "string", "description": "Optional ISO time lower-bound.", "default": ""},
                "limit": {"type": "integer", "description": "Page size.", "default": 20},
                "cursor": {
                    "type": "string",
                    "description": "Offset cursor from previous response (empty for first page).",
                    "default": "",
                },
                "format": {
                    "type": "string",
                    "description": "Output format: text|json",
                    "enum": ["text", "json"],
                    "default": "text",
                },
            },
            "required": ["scope"],
        }

    def execute(
        self,
        scope: str,
        intent: str = "",
        kind: str = "",
        since: str = "",
        limit: int = 20,
        cursor: str = "",
        format: str = "text",
        **kwargs,
    ) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        if hasattr(store, "list_by_scope"):
            payload = store.list_by_scope(scope, intent=intent, kind=kind, since=since, limit=limit, cursor=cursor)
        else:
            payload = store.list_entries_by_scope(scope, intent=intent, since=since, limit=limit, cursor=cursor)
        if str(format).strip().lower() == "json":
            return json.dumps(payload, ensure_ascii=False, indent=2)

        items = payload.get("items", [])
        if not items:
            return (
                f"No memory entries under scope={scope} "
                f"(intent={intent or 'all'}, kind={kind or 'all'}, since={since or 'none'})."
            )
        lines = [
            f"Memory Cards scope={payload.get('scope', scope)} total={payload.get('total', 0)} "
            f"count={payload.get('count', 0)} cursor={cursor or '0'} next_cursor={payload.get('next_cursor', '') or '-'}"
        ]
        for item in items:
            lines.append(
                f"- [{item.get('id', '')}] {item.get('title', '')} | intent={item.get('intent', '') or '-'} | "
                f"updated={item.get('updated_at', '')} | {item.get('summary', '')}"
            )
        return "\n".join(lines)


class MemorySearchTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return "Fallback text search over memory metadata. Prefer memory_nav + memory_list for primary retrieval."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "top_k": {"type": "integer", "description": "Max hits.", "default": 5},
            },
            "required": ["query"],
        }

    def execute(self, query: str, top_k: int = 5, **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        hits = store.search(query, top_k=top_k) if hasattr(store, "search") else store.search_entries(query, top_k=top_k)
        if not hits:
            return "No memory matches."
        lines = []
        for h in hits:
            intent = str(h.get("intent", "")).strip()
            scope = str(h.get("scope", "")).strip()
            meta = []
            if intent:
                meta.append(f"intent={intent}")
            if scope:
                meta.append(f"scope={scope}")
            meta_suffix = f" ({', '.join(meta)})" if meta else ""
            lines.append(f"- [{h.get('id', 'MEM-????')}] {h.get('title', '')}{meta_suffix}: {h.get('summary', '')}")
        return "\n".join(lines)


class MemoryWriteTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "memory_write"

    @property
    def description(self) -> str:
        return "Write a memory entry and update compact memory index."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "Entry type.", "default": "note"},
                "title": {"type": "string", "description": "Entry title."},
                "content": {"type": "string", "description": "Full entry content."},
                "intent": {
                    "type": "string",
                    "description": "Optional write intent label, e.g. job_progress/research_direction/user_preference/insight.",
                    "default": "",
                },
                "scope": {
                    "type": "string",
                    "description": "Optional memory scope, e.g. project, job:<job_id>, user.",
                    "default": "",
                },
                "ttl": {
                    "type": "string",
                    "description": "Optional TTL like 30d/7d/12h. Free text and optional.",
                    "default": "",
                },
                "parent_id": {
                    "type": "string",
                    "description": "Optional parent memory ID.",
                    "default": "",
                },
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                "source": {"type": "string", "description": "Source label.", "default": "agent"},
            },
            "required": ["title", "content"],
        }

    def execute(
        self,
        title: str,
        content: str,
        kind: str = "note",
        intent: str = "",
        scope: str = "",
        ttl: str = "",
        parent_id: str = "",
        tags: Optional[list[str]] = None,
        source: str = "agent",
        **kwargs,
    ) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        normalized_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
        if intent.strip():
            normalized_tags.append(f"intent:{intent.strip()}")
        if scope.strip():
            normalized_tags.append(f"scope:{scope.strip()}")
        if hasattr(store, "add"):
            mem_id = store.add(
                title=title,
                content=content,
                tags=sorted(set(normalized_tags)),
                source=source,
                kind=kind,
                intent=intent,
                scope=scope,
                ttl=(ttl or "").strip() or None,
                parent_id=(parent_id or "").strip() or None,
            )
        else:
            mem_id = store.add_entry(
                title=title,
                content=content,
                tags=sorted(set(normalized_tags)),
                source=source,
                kind=kind,
                intent=intent,
                scope=scope,
            )
        return f"Memory written: {mem_id}"


class ProfileReadTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "profile_read"

    @property
    def description(self) -> str:
        return "Read a project profile by name (e.g., research_core, user_preference)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"profile_name": {"type": "string", "description": "Profile name."}},
            "required": ["profile_name"],
        }

    def execute(self, profile_name: str, **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        data = store.read_profile(profile_name)
        return str(data) if data else f"Profile not found: {profile_name}"


class ProfileWriteTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "profile_write"

    @property
    def description(self) -> str:
        return (
            "Directly write/update a project profile with structured data. "
            "Use this when you have analyzed project content and want to save "
            "the extracted profile (e.g., research_core) without re-running the builder pipeline."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "profile_name": {
                    "type": "string",
                    "description": "Profile name, e.g. 'research_core'.",
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "Structured profile data. For research_core: "
                        "{topic, keywords, stage, target_venue, venue_confidence, summary, ...}"
                    ),
                },
            },
            "required": ["profile_name", "payload"],
        }

    def execute(self, profile_name: str, payload: dict = None, **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        if not payload or not isinstance(payload, dict):
            return "[ERROR] payload must be a non-empty dict."
        try:
            store.write_profile(profile_name, payload)
            store.append_profile_history(profile_name, payload)
            return f"Profile '{profile_name}' updated successfully."
        except Exception as e:
            return f"[ERROR] Failed to write profile: {e}"


class ProfileRefreshTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "profile_refresh"

    @property
    def description(self) -> str:
        return "Refresh project profiles from project content and interaction history."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"profile_name": {"type": "string", "description": "Optional profile name.", "default": "all"}},
        }

    def execute(self, profile_name: str = "all", **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        data = store.refresh_profiles() if hasattr(store, "refresh_profiles") else store.refresh_default_profiles()
        if profile_name == "all":
            return f"Profiles refreshed: {', '.join(data.keys())}"
        if profile_name in data:
            return str(data[profile_name])
        return f"Unknown profile_name: {profile_name}"


class MemoryBriefTool(_KnowledgeTool):
    @property
    def name(self) -> str:
        return "memory_brief"

    @property
    def description(self) -> str:
        return "Return compact project memory brief with profile snapshot and memory IDs."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "index_limit": {
                    "type": "integer",
                    "description": "How many compact memory index lines to include.",
                    "default": 12,
                }
            },
        }

    def execute(self, index_limit: int = 12, **kwargs) -> str:
        store = self._store()
        if not store:
            return "[ERROR] No project context."
        return store.render_system_memory_brief(index_limit=max(index_limit, 1)) or "No memory brief available."
