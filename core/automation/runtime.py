"""Runtime coordinator for project automation jobs."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from agent.radar_autopilot import RadarAutoplanService
from core.automation.bootstrap import ensure_project_automation_jobs
from core.automation.executor import AutomationExecutor
from core.automation.models import AutomationJob
from core.automation.scheduler_aps import APSSchedulerWrapper
from core.automation.settings import (
    GC_PROTECT_JOB_STATE_REFS,
    MIRROR_LEGACY_MEMORY,
    USE_UNIFIED_MEMORY_FOR_AUTOMATION,
)
from core.automation.store_fs import FSAutomationStore
from core.memory import ProjectMemoryStore
from core.profile import ProjectKnowledgeStore
from core.project import Project


class AutomationRuntime:
    """Load, schedule, and execute automation jobs across projects."""

    def __init__(
        self,
        *,
        workspace: Path,
        provider: Any,
        model: str,
        config: Any,
        bus: Optional[Any] = None,
        brave_api_key: Optional[str] = None,
        s2_api_key: Optional[str] = None,
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.config = config
        self.scheduler = APSSchedulerWrapper()
        self.executor = AutomationExecutor(
            provider=provider,
            workspace=workspace,
            model=model,
            config=config,
            bus=bus,
            brave_api_key=brave_api_key,
            s2_api_key=s2_api_key,
        )
        self._running = False
        self._project_job_keys: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        await self.scheduler.start()
        self._running = True
        await self._bootstrap_all_projects()
        # Startup summary
        diag = self.scheduler.get_diagnostics()
        logger.info(
            f"AutomationRuntime ready: "
            f"scheduler={'OK' if diag['aps_running'] else 'DISABLED'} "
            f"projects={len(self._project_job_keys)} "
            f"jobs={diag['registered_count']} "
            f"python={diag['python']}"
        )

    async def stop(self) -> None:
        if not self._running:
            return
        await self.scheduler.stop()
        self._project_job_keys.clear()
        self._running = False

    async def _bootstrap_all_projects(self) -> None:
        if not self.workspace.exists():
            return
        for path in sorted(self.workspace.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            if path.name == "Default":
                continue
            project = Project(path.name, self.workspace)
            await self.bootstrap_project(project)

    def _unschedule_project(self, project_id: str) -> None:
        old_keys = self._project_job_keys.get(project_id, set())
        for key in old_keys:
            self.scheduler.unschedule_job(key)
        self._project_job_keys.pop(project_id, None)

    async def refresh_workspace_projects(self) -> dict[str, Any]:
        """
        Re-scan workspace and reconcile scheduler/project bootstrap state.

        - New project without radar.autoplan -> bootstrap
        - Existing project not tracked by scheduler -> reschedule
        - Removed project directory -> unschedule stale keys
        """
        summary: dict[str, Any] = {
            "scanned": 0,
            "bootstrapped": [],
            "rescheduled": [],
            "removed": [],
            "skipped_disabled": [],
        }

        seen_ids: set[str] = set()
        if self.workspace.exists():
            for path in sorted(self.workspace.iterdir()):
                if not path.is_dir() or path.name.startswith("."):
                    continue
                if path.name == "Default":
                    continue

                project = Project(path.name, self.workspace)
                seen_ids.add(project.id)
                summary["scanned"] += 1

                if project.config.automation and not project.config.automation.enabled:
                    if project.id in self._project_job_keys:
                        self._unschedule_project(project.id)
                    summary["skipped_disabled"].append(project.id)
                    continue

                store = FSAutomationStore(project)
                has_autoplan = bool(store.get_job("radar.autoplan"))
                if not has_autoplan:
                    await self.bootstrap_project(project)
                    summary["bootstrapped"].append(project.id)
                    continue

                if project.id not in self._project_job_keys:
                    await self.reschedule_project(project)
                    summary["rescheduled"].append(project.id)

        stale_project_ids = sorted(set(self._project_job_keys.keys()) - seen_ids)
        for project_id in stale_project_ids:
            self._unschedule_project(project_id)
            summary["removed"].append(project_id)

        return summary

    async def bootstrap_project(self, project: Project) -> None:
        if project.config.automation and not project.config.automation.enabled:
            logger.info(f"Automation disabled in project config: {project.id}")
            return
        async with self._lock:
            try:
                if USE_UNIFIED_MEMORY_FOR_AUTOMATION:
                    memory_store = ProjectMemoryStore(project)
                    migration = memory_store.migrate_runs_from_legacy()
                    if migration.get("migrated"):
                        logger.info(f"Migrated legacy run logs for {project.id}: {migration}")
                    # Only bootstrap if no profile exists yet (cold start).
                    if not memory_store.read_profile("research_core"):
                        memory_store.refresh_profiles()
                else:
                    ks = ProjectKnowledgeStore(project)
                    ks.refresh_default_profiles()
            except Exception as e:
                logger.debug(f"Profile bootstrap skipped for {project.id}: {e}")

            try:
                bootstrap = ensure_project_automation_jobs(project)
                if bootstrap.get("created_autoplan"):
                    logger.info(f"Initialized default automation job [radar.autoplan] for project {project.id}")
                applied = bootstrap.get("radar_applied") or {}
                if int(applied.get("created", 0)) > 0:
                    logger.info(f"Bootstrapped default radar jobs for {project.id}: {applied}")
            except Exception as e:
                logger.debug(f"Default radar bootstrap skipped for {project.id}: {e}")
            await self.reschedule_project(project)

    async def reschedule_project(self, project: Project) -> None:
        store = FSAutomationStore(project)
        project_key = project.id

        old_keys = self._project_job_keys.get(project_key, set())
        for key in old_keys:
            self.scheduler.unschedule_job(key)

        new_keys: set[str] = set()
        for job in store.list_jobs():
            if not job.enabled:
                continue
            key = self._sched_key(project.id, job.id)
            self.scheduler.schedule_job(key, job, lambda j, p=project: self._run_and_log(p, j, "schedule"))
            new_keys.add(key)

        self._project_job_keys[project_key] = new_keys

    async def run_job_now(self, project_id: str, job_id: str, trigger: str = "manual") -> dict[str, Any]:
        project = Project(project_id, self.workspace)
        store = FSAutomationStore(project)
        job = store.get_job(job_id)
        if not job:
            return {"ok": False, "error": f"job not found: {job_id}"}

        run = await self._run_and_log(project, job, trigger)
        return {"ok": run.status == "success", "run": run.to_dict()}

    def list_project_jobs(self, project_id: str) -> list[dict[str, Any]]:
        project = Project(project_id, self.workspace)
        store = FSAutomationStore(project)
        return [j.to_dict() for j in store.list_jobs()]

    async def _run_and_log(self, project: Project, job: AutomationJob, trigger: str) -> Any:
        store = FSAutomationStore(project)
        run = await self.executor.execute_job(project, job, trigger=trigger)
        self._update_job_state_and_memory(project, store, job, run, trigger=trigger)

        # Generate rolling summary (non-blocking on failure)
        await self._update_rolling_summary(project, store, job, run)

        if job.id == "radar.autoplan" and run.status == "success":
            try:
                service = RadarAutoplanService(provider=self.provider, model=self.model)
                result = await service.reconcile_project(
                    project,
                    actor_job_id=job.id,
                    agent_output=run.output_excerpt,
                )
                logger.info(f"Autoplan applied for {project.id}: {result.get('applied', {})}")
                await self.reschedule_project(project)
            except Exception as e:
                logger.warning(f"Autoplan reconcile failed for {project.id}: {e}")

        return run

    @staticmethod
    def _build_run_note(job: AutomationJob, run: Any, trigger: str) -> str:
        summary = (run.output_excerpt or "").strip()
        error = (run.error or "").strip()
        metadata = run.metadata if isinstance(run.metadata, dict) else {}
        token_usage = metadata.get("token_usage", {})
        provider_id = metadata.get("provider_id", "")
        model_name = metadata.get("model_name", "")

        lines = [
            f"Job: {job.id} ({job.name})",
            f"Trigger: {trigger}",
            f"Run ID: {run.run_id}",
            f"Started: {run.started_at}",
            f"Ended: {run.ended_at}",
            f"Status: {run.status}",
        ]
        if model_name or provider_id:
            lines.append(f"Model: {model_name} (provider: {provider_id})")
        if token_usage:
            prompt_t = token_usage.get("prompt_tokens", 0)
            completion_t = token_usage.get("completion_tokens", 0)
            total_t = token_usage.get("total_tokens", 0) or (prompt_t + completion_t)
            lines.append(f"Tokens: {total_t} (prompt: {prompt_t}, completion: {completion_t})")
        lines.append("")
        if summary:
            lines.extend(["Run Summary:", summary[:3000], ""])
        if error:
            lines.extend(["Run Error:", error[:1200]])
        return "\n".join(lines).strip()

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _parse_iso_time(value: Any) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            return None

    @staticmethod
    def _find_agent_written_run(
        memory_store: ProjectMemoryStore,
        *,
        job_id: str,
        started_at: str,
    ) -> Optional[str]:
        """Return the MEM-ID of a job_run entry the agent wrote during this execution, or None."""
        if not started_at:
            return None
        try:
            payload = memory_store.list_by_scope(
                scope=f"job:{job_id}",
                kind="job_run",
                since=started_at,
                limit=5,
            )
            for item in payload.get("items", []):
                if str(item.get("source", "")).strip() != "automation_runtime":
                    return str(item.get("id", "")).strip() or None
        except Exception:
            pass
        return None

    def _maybe_mirror_legacy_memory(self, project: Project, *, job: AutomationJob, run: Any, trigger: str) -> None:
        if not MIRROR_LEGACY_MEMORY:
            return
        try:
            legacy = ProjectKnowledgeStore(project)
            stamp = run.ended_at or run.started_at or datetime.now().isoformat()
            legacy.add_entry(
                kind="job_run",
                intent="job_progress",
                scope=f"job:{job.id}",
                title=f"{job.id} run @ {stamp[:16]}",
                content=self._build_run_note(job, run, trigger),
                tags=["automation", f"job:{job.id}", f"status:{run.status}", f"run:{run.run_id}"],
                source="automation_runtime_mirror",
            )
        except Exception as e:
            logger.debug(f"Failed to mirror legacy memory ({project.id}/{job.id}): {e}")

    def _update_job_state_and_memory(
        self,
        project: Project,
        store: FSAutomationStore,
        job: AutomationJob,
        run: Any,
        *,
        trigger: str,
    ) -> None:
        """Persist run summary into memory and update compact job state."""
        old_state = store.get_job_state(job.id)
        last_entry_id = str(old_state.get("last_entry_id", "")).strip()

        if USE_UNIFIED_MEMORY_FOR_AUTOMATION:
            try:
                memory_store = ProjectMemoryStore(project)
                stamp = run.ended_at or run.started_at or datetime.now().isoformat()
                run_note = self._build_run_note(job, run, trigger)
                run_tags = ["automation", f"job:{job.id}", f"status:{run.status}", f"run:{run.run_id}"]

                # Check if the agent already wrote a job_run entry during this execution.
                # If so, update it with the authoritative runtime info instead of creating a duplicate.
                agent_entry_id = self._find_agent_written_run(
                    memory_store, job_id=job.id, started_at=run.started_at,
                )
                if agent_entry_id:
                    memory_store.update(agent_entry_id, {
                        "title": f"{job.id} run @ {stamp[:16]}",
                        "content": run_note,
                        "tags": run_tags,
                        "source": "automation_runtime",
                        "ttl": "30d",
                    })
                    last_entry_id = agent_entry_id
                else:
                    last_entry_id = memory_store.add(
                        kind="job_run",
                        intent="job_progress",
                        scope=f"job:{job.id}",
                        title=f"{job.id} run @ {stamp[:16]}",
                        content=run_note,
                        tags=run_tags,
                        source="automation_runtime",
                        ttl="30d",
                        created_at=run.started_at,
                    )
                memory_store.gc(protect_job_state_refs=GC_PROTECT_JOB_STATE_REFS)
            except Exception as e:
                logger.debug(f"Failed to write unified run memory ({project.id}/{job.id}): {e}")
            self._maybe_mirror_legacy_memory(project, job=job, run=run, trigger=trigger)
        else:
            try:
                legacy = ProjectKnowledgeStore(project)
                stamp = run.ended_at or run.started_at or datetime.now().isoformat()
                last_entry_id = legacy.add_entry(
                    kind="job_run",
                    intent="job_progress",
                    scope=f"job:{job.id}",
                    title=f"{job.id} run @ {stamp[:16]}",
                    content=self._build_run_note(job, run, trigger),
                    tags=["automation", f"job:{job.id}", f"status:{run.status}", f"run:{run.run_id}"],
                    source="automation_runtime",
                )
            except Exception as e:
                logger.debug(f"Failed to write legacy run memory ({project.id}/{job.id}): {e}")

        run_count = self._safe_int(old_state.get("run_count"), 0) + 1
        started_at = run.started_at or ""
        ended_at = run.ended_at or run.started_at or ""
        started_dt = self._parse_iso_time(started_at)
        ended_dt = self._parse_iso_time(ended_at)
        if started_dt and ended_dt and ended_dt >= started_dt:
            last_duration_seconds = int((ended_dt - started_dt).total_seconds())
        else:
            last_duration_seconds = 0

        total_duration_seconds = self._safe_int(old_state.get("total_duration_seconds"), 0) + last_duration_seconds
        if str(run.status).lower() == "failed":
            consecutive_failures = self._safe_int(old_state.get("consecutive_failures"), 0) + 1
        else:
            consecutive_failures = 0

        # Token usage from run metadata
        run_meta = run.metadata if isinstance(run.metadata, dict) else {}
        run_token_usage = run_meta.get("token_usage", {})
        last_total_tokens = self._safe_int(run_token_usage.get("total_tokens"), 0) or (
            self._safe_int(run_token_usage.get("prompt_tokens"), 0)
            + self._safe_int(run_token_usage.get("completion_tokens"), 0)
        )
        total_tokens = self._safe_int(old_state.get("total_tokens"), 0) + last_total_tokens

        patch: dict[str, Any] = {
            "last_started_at": started_at,
            "last_ended_at": ended_at,
            "last_run_at": ended_at,
            "last_status": run.status,
            "last_entry_id": last_entry_id,
            "run_count": run_count,
            "last_duration_seconds": last_duration_seconds,
            "total_duration_seconds": total_duration_seconds,
            "consecutive_failures": consecutive_failures,
            "last_token_usage": run_token_usage,
            "last_total_tokens": last_total_tokens,
            "total_tokens": total_tokens,
            "last_provider_id": run_meta.get("provider_id", ""),
            "last_model_name": run_meta.get("model_name", ""),
        }

        try:
            store.update_job_state(job.id, patch)
        except Exception as e:
            logger.debug(f"Failed to update job state ({project.id}/{job.id}): {e}")

    async def _update_rolling_summary(
        self,
        project: Project,
        store: FSAutomationStore,
        job: AutomationJob,
        run: Any,
    ) -> None:
        """Generate a rolling summary via LLM and store in job_state.

        Final structure:
          1) LLM cumulative summary (naturally incorporates agent-mentioned MEM refs)
          2) Programmatic: this run's job_run MEM entry ref + retrieval hints
        """
        try:
            job_state = store.get_job_state(job.id)
            prev_summary = str(job_state.get("rolling_summary", "")).strip()
            last_entry_id = str(job_state.get("last_entry_id", "")).strip()
            output = (run.output_excerpt or "").strip()[:2000]

            # --- Part 1: LLM rolling summary ---
            prev_len = len(prev_summary) if prev_summary else 0
            if prev_len > 2000:
                compress_hint = (
                    f"已接近 2000 字上限，请在保留上述所有要点的前提下压缩早期细节，"
                    f"优先保留：记忆条目索引、去重所需的论文ID/关键词列表、未解决的注意事项。"
                )
            else:
                compress_hint = "字数充裕，可保留更多细节。"
            prompt = (
                "你是一个定时任务执行历史的总结助手。请基于以下信息，更新该任务的滚动执行总结。\n\n"
                f"任务: {job.id} ({job.name})\n\n"
                "## 上次滚动总结\n"
                f"（当前长度: {prev_len} 字）\n"
                f"{prev_summary or '(首次执行，无历史总结)'}\n\n"
                "## 本次执行结果\n"
                f"状态: {run.status}\n"
                f"时间: {run.started_at} ~ {run.ended_at}\n"
                f"输出摘要:\n{output}\n\n"
                "## 要求\n"
                "生成该任务的累计滚动总结（上限 2000 字），涵盖：\n"
                "- 整体执行情况（成功率、执行次数趋势）\n"
                "- 已完成的关键动作摘要（搜过的关键词、推送的论文ID、发过的文件等）——用于去重\n"
                "- 记忆条目索引：列出 agent 写入的记忆条目（MEM-xxxx），保留最近 3-10 条（根据信息密度自行判断），"
                "格式为 `MEM-xxxx: 一句话用途说明`。早于这个窗口的条目可压缩为一行计数摘要"
                "（如「更早记录: MEM-0038~MEM-0054，共 9 条，主要涉及 xxx」）。\n"
                "- 需要下次注意的事项\n\n"
                f"重要：上次总结已有 {prev_len} 字。{compress_hint}\n\n"
                "只输出总结文本，不要多余的包裹格式或标题。"
            )

            resp = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                tools=None,
            )
            llm_summary = (resp.content or "").strip()
            if not llm_summary:
                return

            # --- Part 2: Programmatic entry ref + retrieval hints ---
            parts = [llm_summary]
            if last_entry_id:
                parts.append(f"\n本次执行记录: {last_entry_id}")
            parts.append(
                f"\n检索提示: "
                f"memory_list(scope='job:{job.id}', kind='job_run') 获取全部执行记录; "
                f"memory_list(scope='job:{job.id}') 获取全部条目(含 agent 特殊记忆); "
                f"memory_get(id) 获取具体条目全文。"
            )

            final_summary = "\n".join(parts)
            store.update_job_state(job.id, {"rolling_summary": final_summary})
            logger.debug(f"Rolling summary updated for {project.id}/{job.id} ({len(final_summary)} chars)")
        except Exception as e:
            logger.warning(f"Rolling summary generation failed for {project.id}/{job.id}: {e}")

    @staticmethod
    def _sched_key(project_id: str, job_id: str) -> str:
        return f"automation:{project_id}:{job_id}"
