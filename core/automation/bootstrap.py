"""Shared helpers for project automation bootstrap."""

from __future__ import annotations

from typing import Any

from core.automation.models import AutomationJob, JobSchedule, OutputPolicy
from core.automation.radar_defaults import maybe_bootstrap_default_radar_jobs
from core.automation.store_fs import FSAutomationStore


def ensure_project_automation_jobs(project: Any) -> dict[str, Any]:
    """Ensure required system automation jobs exist for a project."""
    if not project:
        return {"ok": False, "reason": "no_project"}
    if getattr(project, "is_default", False):
        return {"ok": False, "reason": "default_project"}
    if project.config.automation and not project.config.automation.enabled:
        return {"ok": False, "reason": "automation_disabled"}

    store = FSAutomationStore(project)
    created_autoplan = False

    if not store.get_job("radar.autoplan"):
        timezone = "UTC"
        schedule = "0 */12 * * *"
        if project.config.automation:
            timezone = project.config.automation.timezone or "UTC"
            if project.config.automation.autoplan and project.config.automation.autoplan.schedule:
                schedule = project.config.automation.autoplan.schedule

        store.upsert_job(
            AutomationJob(
                id="radar.autoplan",
                name="Radar Autoplan",
                type="normal",
                schedule=JobSchedule(cron=schedule, timezone=timezone),
                prompt=(
                    "你是雷达任务自动编排器。请基于项目内容、用户交互偏好和现有任务，"
                    "判断是否需要新增/更新系统雷达任务。输出 JSON 决策并给出理由。\n\n"
                    "上下文说明：系统已自动注入你的执行历史总结（rolling_summary）和近期运行记录，"
                    "直接参考即可，无需手动读取历史。\n"
                    "如需查看更早的详情，可用 memory_nav(domain='job') → memory_list(scope='job:radar.autoplan') → memory_get(id)。\n"
                    "执行记录由系统自动生成，不要写 kind='job_run' 的条目。\n"
                    "如有需要长期保留的决策记录，可调用 memory_write，kind 自定义（如 'plan_decision'），"
                    "scope='job:radar.autoplan'。"
                ),
                enabled=True,
                managed_by="system",
                output_policy=OutputPolicy(mode="default"),
                metadata={"system_job": True, "origin": "system"},
            )
        )
        created_autoplan = True

    applied = {
        "template_group": "",
        "template_version": "",
        "created": 0,
        "updated": 0,
        "disabled": 0,
        "skipped": 0,
        "jobs": [],
        "reason": "gateway_hub_skip",
    }
    if project.id != "gateway_hub":
        applied = maybe_bootstrap_default_radar_jobs(store)

    return {
        "ok": True,
        "created_autoplan": created_autoplan,
        "radar_applied": applied,
    }

