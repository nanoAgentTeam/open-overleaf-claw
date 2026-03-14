"""Generalized automation runtime for scheduled project jobs."""

from core.automation.bootstrap import ensure_project_automation_jobs
from core.automation.models import AutomationJob, JobRun, JobSchedule, OutputPolicy
from core.automation.prompt_context import AutomationPromptContextBuilder
from core.automation.radar_defaults import apply_default_radar_jobs, maybe_bootstrap_default_radar_jobs
from core.automation.runtime import AutomationRuntime
from core.automation.store_fs import FSAutomationStore

__all__ = [
    "AutomationJob",
    "AutomationPromptContextBuilder",
    "AutomationRuntime",
    "FSAutomationStore",
    "JobRun",
    "JobSchedule",
    "OutputPolicy",
    "ensure_project_automation_jobs",
    "apply_default_radar_jobs",
    "maybe_bootstrap_default_radar_jobs",
]
