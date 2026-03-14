"""Unified context renderer for automation/autoplan memory prompts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from core.memory.store import ProjectMemoryStore

if TYPE_CHECKING:
    from core.automation.models import AutomationJob


class ContextRenderer:
    """Build shared memory context blocks across automation consumers."""

    def __init__(self, store: ProjectMemoryStore):
        self.store = store

    @staticmethod
    def _trim(text: str, limit: int = 220) -> str:
        raw = (text or "").strip().replace("\n", " ")
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "..."

    def render_base_brief(self, index_limit: int = 12) -> str:
        research = self.store.read_profile("research_core")
        user_pref = self.store.read_profile("user_preference")
        trajectory = self.store.summarize_research_trajectory(limit=5)
        compact_index = self.store.read_compact_index(limit=max(index_limit, 1))

        lines: list[str] = []

        if research:
            keywords = research.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            kw_text = ", ".join(str(k) for k in keywords[:8] if str(k).strip())
            lines.extend(
                [
                    "项目研究快照:",
                    f"- topic: {research.get('topic', '-')}",
                    f"- stage: {research.get('stage', '-')}",
                    f"- keywords: {kw_text or '-'}",
                ]
            )

        if user_pref:
            prefs = user_pref.get("preferences", {}) if isinstance(user_pref.get("preferences"), dict) else {}
            focus = prefs.get("focus", [])
            if not isinstance(focus, list):
                focus = []
            lines.extend(
                [
                    "用户偏好快照:",
                    f"- push_style: {prefs.get('push_style', '-')}",
                    f"- language: {prefs.get('language', '-')}",
                    f"- focus: {', '.join(str(x) for x in focus if str(x).strip()) or '-'}",
                ]
            )

        if trajectory:
            lines.append("研究方向近期轨迹:")
            lines.append(trajectory)

        if compact_index:
            lines.append("记忆索引（可用 memory_get 按 ID 拉取全文）:")
            lines.append(compact_index)

        return "\n".join(lines).strip()

    def render_job_context(
        self,
        job: "AutomationJob",
        job_state: dict[str, Any],
        recent_entries: list[dict[str, Any]],
    ) -> str:
        brief = self.render_base_brief(index_limit=10)
        lines: list[str] = [
            "[AUTOMATION CONTEXT]",
            f"你正在执行任务: {job.id} ({job.name})",
            "执行约束:",
            "- 只有在确实需要通知时才调用 notify_push；不需要通知就不要推送。",
            "- 如需长期保留信息，调用 memory_write，并使用 intent/scope 标注写入意图与范围。",
            f"- 任务相关记忆建议 scope 使用 job:{job.id}。",
            "- 记忆检索主路径：memory_nav -> memory_list(scope=...) -> memory_get(MEM-xxxx)。",
            "- memory_search 仅作为兜底，不作为首选路径。",
        ]

        if brief:
            lines.append(brief)

        if job_state:
            lines.extend(
                [
                    "该任务近期状态:",
                    f"- last_run_at: {job_state.get('last_run_at', '-')}",
                    f"- last_status: {job_state.get('last_status', '-')}",
                    f"- last_entry_id: {job_state.get('last_entry_id', '-')}",
                    f"- run_count: {job_state.get('run_count', '-')}",
                    f"- consecutive_failures: {job_state.get('consecutive_failures', '-')}",
                ]
            )

        rolling_summary = str(job_state.get("rolling_summary", "")).strip()
        if rolling_summary:
            lines.append("该任务执行历史总结:")
            lines.append(rolling_summary)

        if recent_entries:
            lines.append("该任务近期运行记录:")
            for item in recent_entries[:3]:
                stamp = item.get("updated_at") or item.get("created_at") or "unknown_time"
                lines.append(
                    f"- [{item.get('id', '')}] {item.get('title', '')} @ {stamp[:16]} | {self._trim(str(item.get('summary', '')))}"
                )

        return "\n".join(lines).strip()

    def render_autoplan_context(
        self,
        jobs: list[dict[str, Any]],
        states: dict[str, dict[str, Any]],
        recent_entries: list[dict[str, Any]],
    ) -> str:
        brief = self.render_base_brief(index_limit=20)
        lines: list[str] = []
        if brief:
            lines.append(brief)

        lines.append("现有作业（JSON）:")
        lines.append(json.dumps(jobs, ensure_ascii=False))
        lines.append("作业状态（JSON）:")
        lines.append(json.dumps(states, ensure_ascii=False))

        lines.append("近期运行记录（kind=job_run）:")
        if not recent_entries:
            lines.append("(empty)")
        else:
            for item in recent_entries[:10]:
                scope = str(item.get("scope", ""))
                lines.append(
                    f"- [{item.get('id', '')}] {scope} | {item.get('title', '')} | {self._trim(str(item.get('summary', '')))}"
                )

        return "\n".join(lines).strip()
