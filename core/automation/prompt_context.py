"""Deprecated compatibility wrapper for automation prompt context."""

from __future__ import annotations

from typing import Any

from core.automation.models import AutomationJob
from core.automation.store_fs import FSAutomationStore
from core.memory import ContextRenderer, ProjectMemoryStore


class AutomationPromptContextBuilder:
    """Backward-compatible adapter. Prefer ContextRenderer directly."""

    def __init__(self, project: Any, job: AutomationJob, store: FSAutomationStore | None = None):
        self.project = project
        self.job = job
        self.store = store or FSAutomationStore(project)

    def render(self) -> str:
        memory_store = ProjectMemoryStore(self.project)
        try:
            # Only bootstrap if no profile exists yet (cold start).
            if not memory_store.read_profile("research_core"):
                memory_store.refresh_profiles()
        except Exception:
            pass

        job_state = self.store.get_job_state(self.job.id)
        recent_entries = memory_store.list_by_scope(
            scope=f"job:{self.job.id}",
            kind="job_run",
            limit=3,
        ).get("items", [])
        renderer = ContextRenderer(memory_store)
        return renderer.render_job_context(job=self.job, job_state=job_state, recent_entries=recent_entries)
