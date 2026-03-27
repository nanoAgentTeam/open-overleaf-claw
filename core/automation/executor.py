"""Execution engine for automation jobs."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from agent.loop import AgentLoop
from bus.queue import MessageBus
from core.automation.models import AutomationJob, JobRun
from core.automation.store_fs import FSAutomationStore
from core.memory import ContextRenderer, ProjectMemoryStore


class _UsageCollector:
    """Lightweight on_event callback that accumulates LLM token usage."""

    def __init__(self):
        self.token_usage: dict[str, int] = {}

    def __call__(self, event: Any) -> None:
        try:
            from agent.memory.trace import EventType
            if event.type == EventType.LLM_END and event.token_usage:
                for k, v in event.token_usage.items():
                    self.token_usage[k] = self.token_usage.get(k, 0) + int(v)
        except Exception:
            pass


class AutomationExecutor:
    """Run normal/task automation jobs in project-scoped agent sessions."""

    def __init__(
        self,
        *,
        provider: Any,
        workspace: Path,
        model: str,
        config: Any,
        bus: Optional[MessageBus] = None,
        brave_api_key: Optional[str] = None,
        s2_api_key: Optional[str] = None,
    ):
        self.provider = provider
        self.workspace = workspace
        self.model = model
        self.config = config
        self.bus = bus
        self.brave_api_key = brave_api_key
        self.s2_api_key = s2_api_key

    def _get_provider_info(self) -> dict[str, str]:
        """Extract current active provider id and model name from config."""
        try:
            active = self.config.get_active_provider()
            if active:
                return {
                    "provider_id": active.id or "",
                    "model_name": active.model_name or self.model,
                }
        except Exception:
            pass
        return {"provider_id": "", "model_name": self.model}

    async def execute_job(self, project: Any, job: AutomationJob, trigger: str = "schedule") -> JobRun:
        run = JobRun(
            run_id=f"run_{uuid.uuid4().hex[:12]}",
            project_id=project.id,
            job_id=job.id,
            trigger=trigger,
            started_at=datetime.now().isoformat(),
            status="running",
        )

        if not job.enabled:
            run.status = "skipped"
            run.ended_at = datetime.now().isoformat()
            run.output_excerpt = "Job disabled"
            return run

        prompt = job.prompt
        try:
            memory_store = ProjectMemoryStore(project)
            try:
                # Only bootstrap if no profile exists yet (cold start).
                if not memory_store.read_profile("research_core"):
                    memory_store.refresh_profiles(provider=self.provider, model=self.model)
            except Exception:
                pass

            control_store = FSAutomationStore(project)
            job_state = control_store.get_job_state(job.id)
            recent_entries = memory_store.list_by_scope(
                scope=f"job:{job.id}",
                limit=5,
            ).get("items", [])
            context_block = ContextRenderer(memory_store).render_job_context(
                job=job,
                job_state=job_state,
                recent_entries=recent_entries,
            )
            if context_block:
                prompt = (
                    f"{context_block}\n\n"
                    "[JOB INSTRUCTION]\n"
                    f"{job.prompt}\n\n"
                    "执行提醒:\n"
                    "- 输出尽量面向行动，不必拘泥固定字段。\n"
                    "- 推送规则（严格执行）：\n"
                    "  - 了解情况型任务（daily.scan/weekly.digest/conference.track/profile.refresh）：\n"
                    "    只要本次执行发现了与项目相关的新内容，必须调用 notify_push 推送完整报告。\n"
                    "  - 预警型任务（urgent.alert/direction.drift）：\n"
                    "    仅在检测到真实威胁（竞争论文、截稿临近、方向漂移）时推送。\n"
                    "  - 若 notify_push 返回 'no channels configured'，不影响任务，继续执行。\n"
                    "  - ⚠️ 重要：notify_push 的 content 必须是完整报告，不是摘要。\n"
                    "    用户无法看到对话内容，推送是唯一渠道。\n"
                    "    禁止在推送中写「详情见对话框」「更多详情见对话」等引导语。\n"
                    "    所有论文的完整信息都必须包含在 notify_push 的 content 中。\n"
                    "- 如需长期记录，显式调用 memory_write 并填写 intent/scope。"
                )
        except Exception as e:
            logger.debug(f"Automation prompt context fallback for {project.id}/{job.id}: {e}")

        if job.type == "task":
            prompt = f"/task --auto {prompt}"

        usage_collector = _UsageCollector()
        try:
            bus = self.bus or MessageBus()
            from agent.tools.loader import ToolLoader
            _auto_profile = ToolLoader._load_profile("automation_agent")
            _auto_role_type = _auto_profile.get("role_type", "Assistant")
            session = project.session("automation", role_type=_auto_role_type)

            loop = AgentLoop(
                bus=bus,
                provider=self.provider,
                workspace=self.workspace,
                model=self.model,
                brave_api_key=self.brave_api_key,
                s2_api_key=self.s2_api_key,
                project_id=project.id,
                session_id=session.id,
                mode="NORMAL",
                role_name="Assistant",
                profile="automation_agent",
                config=self.config,
                project=project,
                session=session,
            )

            result = await loop.process_direct(
                prompt,
                session_key=f"automation:{project.id}:{job.id}",
                on_event=usage_collector,
            )
            run.status = "success"
            run.output_excerpt = (result or "").strip()
            provider_info = self._get_provider_info()
            run.metadata = {
                "job_type": job.type,
                "token_usage": usage_collector.token_usage,
                "provider_id": provider_info["provider_id"],
                "model_name": provider_info["model_name"],
            }
        except Exception as e:
            logger.error(f"Automation job execution failed ({project.id}/{job.id}): {e}")
            run.status = "failed"
            run.error = str(e)
            run.metadata = {
                "job_type": job.type,
                "token_usage": usage_collector.token_usage,
                **self._get_provider_info(),
            }
        finally:
            run.ended_at = datetime.now().isoformat()

        return run
