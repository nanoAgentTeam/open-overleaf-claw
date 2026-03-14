"""APScheduler wrapper for automation jobs."""

from __future__ import annotations

import asyncio
import inspect
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from core.automation.models import AutomationJob

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    HAS_APSCHEDULER = True
except Exception:
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]
    HAS_APSCHEDULER = False


class APSSchedulerWrapper:
    """Thin adapter over APScheduler with safe no-op fallback when unavailable."""

    # Heartbeat interval in seconds (default 30 min)
    HEARTBEAT_INTERVAL = 1800

    def __init__(self):
        self._running = False
        self._scheduler: Any = None
        self._registered_keys: set[str] = set()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._started_at: Optional[str] = None

    @property
    def available(self) -> bool:
        return HAS_APSCHEDULER

    async def start(self) -> None:
        if not HAS_APSCHEDULER:
            logger.error(
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  APScheduler NOT INSTALLED — all cron jobs are DISABLED ║\n"
                "║  Fix: pip install apscheduler  (or use .venv Python)    ║\n"
                f"║  Current Python: {sys.executable:<40s} ║\n"
                "╚══════════════════════════════════════════════════════════╝"
            )
            return
        if self._running:
            return
        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        self._running = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        logger.info(f"Automation scheduler started. Python: {sys.executable}")
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

    async def stop(self) -> None:
        if not self._running:
            return
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        self._registered_keys.clear()
        self._running = False
        logger.info("Automation scheduler stopped.")

    def schedule_job(
        self,
        key: str,
        job: AutomationJob,
        callback: Callable[[AutomationJob], Awaitable[None] | None],
    ) -> None:
        if not HAS_APSCHEDULER or not self._scheduler:
            logger.debug(f"Skipping schedule for {job.id}: APScheduler unavailable")
            return
        if key in self._registered_keys:
            self.unschedule_job(key)

        try:
            trigger = CronTrigger.from_crontab(job.schedule.cron, timezone=job.schedule.timezone)
        except Exception as e:
            logger.warning(f"Invalid cron for job {job.id}: {job.schedule.cron} ({e})")
            return

        async def _run() -> None:
            logger.info(f"Cron fired: {job.id} (key={key})")
            try:
                result = callback(job)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.error(f"Scheduled job callback failed for {job.id}: {e}")

        self._scheduler.add_job(
            _run, trigger=trigger, id=key,
            replace_existing=True, coalesce=True, max_instances=1,
            misfire_grace_time=3600,
        )
        self._registered_keys.add(key)

        # Log next fire time for this job
        next_fire = self._get_next_fire_time(key)
        next_str = next_fire if next_fire else "unknown"
        logger.info(f"Scheduled [{key}] cron='{job.schedule.cron}' tz={job.schedule.timezone} next_fire={next_str}")

    def unschedule_job(self, key: str) -> None:
        if not HAS_APSCHEDULER or not self._scheduler:
            return
        try:
            self._scheduler.remove_job(key)
        except Exception:
            pass
        self._registered_keys.discard(key)

    def list_scheduled_keys(self) -> list[str]:
        return sorted(self._registered_keys)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return scheduler diagnostics for debug API / logging."""
        aps_running = False
        aps_jobs: list[dict[str, Any]] = []
        if self._scheduler:
            aps_running = getattr(self._scheduler, "running", False)
            if aps_running:
                try:
                    for j in self._scheduler.get_jobs():
                        aps_jobs.append({
                            "id": j.id,
                            "next_run_time": str(j.next_run_time) if j.next_run_time else None,
                            "pending": j.pending,
                        })
                except Exception:
                    pass
        return {
            "scheduler_available": HAS_APSCHEDULER,
            "scheduler_running": self._running,
            "aps_running": aps_running,
            "started_at": self._started_at,
            "registered_count": len(self._registered_keys),
            "registered_keys": self.list_scheduled_keys(),
            "aps_jobs": aps_jobs,
            "python": sys.executable,
        }

    def _get_next_fire_time(self, key: str) -> Optional[str]:
        if not self._scheduler:
            return None
        try:
            j = self._scheduler.get_job(key)
            if j and j.next_run_time:
                return j.next_run_time.isoformat()
        except Exception:
            pass
        return None

    async def _heartbeat_loop(self) -> None:
        """Periodic log to confirm scheduler is alive."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                if not self._running:
                    break
                diag = self.get_diagnostics()
                upcoming = []
                for j in diag.get("aps_jobs", []):
                    if j.get("next_run_time"):
                        upcoming.append(f"{j['id']}@{j['next_run_time'][:16]}")
                logger.info(
                    f"Scheduler heartbeat: running={diag['aps_running']} "
                    f"jobs={diag['registered_count']} "
                    f"upcoming=[{', '.join(upcoming[:5])}{'...' if len(upcoming) > 5 else ''}]"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Scheduler heartbeat error: {e}")
