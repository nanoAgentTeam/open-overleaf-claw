"""Filesystem-backed store for project automation jobs and lightweight states."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from core.automation.models import AutomationJob


class FSAutomationStore:
    """Project-scoped filesystem store for automation control-plane data."""
    _DEPRECATED_STATE_KEYS = (
        "last_note_ref",
        "last_run_id",
        "last_error",
        "last_trigger",
    )

    def __init__(self, project: Any):
        self.project = project
        self.project_id = project.id

        self.base_dir = project.root / ".project_memory"
        self.jobs_dir = self.base_dir / "jobs"
        self.states_dir = self.base_dir / "job_states"
        self.subscriptions_file = self.base_dir / "subscriptions.json"

        self.legacy_base_dir = project.root / ".project_memory" / "automation"
        self.legacy_jobs_dir = self.legacy_base_dir / "jobs"
        self.legacy_states_dir = self.legacy_base_dir / "job_states"
        self.legacy_subscriptions_file = self.legacy_base_dir / "subscriptions.json"

        self._ensure_dirs()
        self._migrate_legacy_layout()

    def _ensure_dirs(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.states_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(raw: str) -> str:
        safe = "".join(ch for ch in raw.strip() if ch.isalnum() or ch in ("-", "_", "."))
        return safe or "job"

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{self._safe_name(job_id)}.json"

    def _state_path(self, job_id: str) -> Path:
        return self.states_dir / f"{self._safe_name(job_id)}.json"

    def _atomic_write_json(self, target: Path, payload: dict[str, Any]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    def _copy_if_missing(self, src: Path, dst: Path) -> bool:
        if not src.exists() or dst.exists() or not src.is_file():
            return False
        try:
            payload = json.loads(src.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
            self._atomic_write_json(dst, payload)
            return True
        except Exception as e:
            logger.debug(f"Failed to migrate legacy file {src} -> {dst}: {e}")
            return False

    def _migrate_legacy_layout(self) -> None:
        moved = 0
        if self.legacy_jobs_dir.exists():
            for src in self.legacy_jobs_dir.glob("*.json"):
                dst = self.jobs_dir / src.name
                if self._copy_if_missing(src, dst):
                    moved += 1

        if self.legacy_states_dir.exists():
            for src in self.legacy_states_dir.glob("*.json"):
                dst = self.states_dir / src.name
                if self._copy_if_missing(src, dst):
                    moved += 1

        if self._copy_if_missing(self.legacy_subscriptions_file, self.subscriptions_file):
            moved += 1

        if moved > 0:
            logger.info(f"Migrated legacy automation control files for {self.project_id}: {moved}")

    def list_jobs(self) -> list[AutomationJob]:
        jobs: list[AutomationJob] = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = AutomationJob.from_dict(data)
                if not job.id:
                    job.id = path.stem
                jobs.append(job)
            except Exception as e:
                logger.warning(f"Failed to load job from {path}: {e}")
        return jobs

    def get_job(self, job_id: str) -> Optional[AutomationJob]:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            job = AutomationJob.from_dict(data)
            if not job.id:
                job.id = job_id
            return job
        except Exception as e:
            logger.warning(f"Failed to load job {job_id}: {e}")
            return None

    def upsert_job(self, job: AutomationJob) -> None:
        if not job.id:
            raise ValueError("job.id is required")
        job.updated_at = datetime.now().isoformat()
        self._atomic_write_json(self._job_path(job.id), job.to_dict())

    def disable_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if not job:
            return False
        job.enabled = False
        self.upsert_job(job)
        return True

    def freeze_job(self, job_id: str) -> bool:
        """Mark a job as frozen so autoplan cannot modify it."""
        job = self.get_job(job_id)
        if not job:
            return False
        job.frozen = True
        self.upsert_job(job)
        return True

    def unfreeze_job(self, job_id: str) -> bool:
        """Unfreeze a job so autoplan can manage it again."""
        job = self.get_job(job_id)
        if not job:
            return False
        job.frozen = False
        self.upsert_job(job)
        return True

    def delete_job(self, job_id: str) -> bool:
        path = self._job_path(job_id)
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        return True

    def get_job_state(self, job_id: str) -> dict[str, Any]:
        path = self._state_path(job_id)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to load job state {job_id}: {e}")
            return {}

    def update_job_state(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("patch must be a dict")
        state = self.get_job_state(job_id)
        state.update(patch)
        for key in self._DEPRECATED_STATE_KEYS:
            state.pop(key, None)
        state["job_id"] = job_id
        state["updated_at"] = datetime.now().isoformat()
        self._atomic_write_json(self._state_path(job_id), state)
        return state

    def get_subscriptions(self) -> dict[str, list[str]]:
        if not self.subscriptions_file.exists():
            return {}
        try:
            data = json.loads(self.subscriptions_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            result: dict[str, list[str]] = {}
            for ch, chat_ids in data.items():
                if ch == "_linked_ids":
                    continue
                if not isinstance(chat_ids, list):
                    continue
                ids = [str(i).strip() for i in chat_ids if str(i).strip()]
                if ids:
                    result[str(ch)] = sorted(set(ids))
            return result
        except Exception as e:
            logger.warning(f"Failed to load subscriptions: {e}")
            return {}

    def get_linked_subscription_ids(self) -> list[str]:
        if not self.subscriptions_file.exists():
            return []
        try:
            data = json.loads(self.subscriptions_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return []
            raw = data.get("_linked_ids", [])
            if not isinstance(raw, list):
                return []
            return [str(i).strip() for i in raw if str(i).strip()]
        except Exception as e:
            logger.warning(f"Failed to load linked subscription ids: {e}")
            return []

    def set_linked_subscription_ids(self, ids: list[str]) -> None:
        if self.subscriptions_file.exists():
            try:
                data = json.loads(self.subscriptions_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
        else:
            data = {}
        cleaned = sorted(set(str(i).strip() for i in ids if str(i).strip()))
        data["_linked_ids"] = cleaned
        self._atomic_write_json(self.subscriptions_file, data)

    def _read_raw_subscriptions(self) -> dict[str, Any]:
        """Read the raw subscriptions JSON, preserving all fields including _linked_ids."""
        if not self.subscriptions_file.exists():
            return {}
        try:
            data = json.loads(self.subscriptions_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to read raw subscriptions: {e}")
            return {}

    def add_subscription(self, channel: str, chat_id: str) -> None:
        channel = str(channel).strip()
        chat_id = str(chat_id).strip()
        if not channel or not chat_id:
            raise ValueError("channel and chat_id are required")
        data = self._read_raw_subscriptions()
        existing = data.get(channel, [])
        if not isinstance(existing, list):
            existing = []
        bucket = set(str(i).strip() for i in existing if str(i).strip())
        bucket.add(chat_id)
        data[channel] = sorted(bucket)
        self._atomic_write_json(self.subscriptions_file, data)

    def remove_subscription(self, channel: str, chat_id: str) -> None:
        data = self._read_raw_subscriptions()
        if channel not in data:
            return
        existing = data.get(channel, [])
        if not isinstance(existing, list):
            return
        data[channel] = [cid for cid in existing if str(cid).strip() != chat_id]
        if not data[channel]:
            data.pop(channel, None)
        self._atomic_write_json(self.subscriptions_file, data)
