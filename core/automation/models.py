"""Data models for generalized scheduled automation jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


SUPPORTED_JOB_TYPES = {"normal", "task"}


@dataclass
class JobSchedule:
    """Cron-based schedule for a job."""

    cron: str
    timezone: str = "UTC"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobSchedule":
        return cls(
            cron=str(data.get("cron", "0 9 * * *")).strip() or "0 9 * * *",
            timezone=str(data.get("timezone", "UTC")).strip() or "UTC",
        )

    def to_dict(self) -> dict[str, Any]:
        return {"cron": self.cron, "timezone": self.timezone}


@dataclass
class OutputPolicy:
    """
    Optional output policy.

    mode=default means channels will be resolved by notify tools if the
    caller does not provide channels explicitly.
    """

    mode: str = "default"
    channels: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OutputPolicy":
        if not data:
            return cls()
        raw_channels = data.get("channels", [])
        channels = [str(ch).strip() for ch in raw_channels if str(ch).strip()] if isinstance(raw_channels, list) else []
        return cls(
            mode=str(data.get("mode", "default")).strip() or "default",
            channels=channels,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {"mode": self.mode}
        if self.channels:
            payload["channels"] = self.channels
        return payload


@dataclass
class AutomationJob:
    """
    Generalized scheduled job.

    Core shape: prompt + type(normal/task) + schedule.
    """

    id: str
    name: str
    type: str
    schedule: JobSchedule
    prompt: str
    enabled: bool = True
    managed_by: str = "system"  # system | user (origin label, not permission boundary)
    frozen: bool = False  # user lock: when True, autoplan cannot modify this job
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutomationJob":
        job_type = str(data.get("type", "normal")).strip().lower()
        if job_type not in SUPPORTED_JOB_TYPES:
            job_type = "normal"

        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip() or str(data.get("id", "Unnamed Job")),
            type=job_type,
            schedule=JobSchedule.from_dict(data.get("schedule", {})),
            prompt=str(data.get("prompt", "")).strip(),
            enabled=bool(data.get("enabled", True)),
            managed_by=str(data.get("managed_by", "system")).strip() or "system",
            frozen=bool(data.get("frozen", False)),
            output_policy=OutputPolicy.from_dict(data.get("output_policy")),
            updated_at=str(data.get("updated_at", datetime.now().isoformat())),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "schedule": self.schedule.to_dict(),
            "prompt": self.prompt,
            "enabled": self.enabled,
            "managed_by": self.managed_by,
            "frozen": self.frozen,
            "output_policy": self.output_policy.to_dict(),
            "updated_at": self.updated_at,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class JobRun:
    """Execution log record for a scheduled/manual job run."""

    run_id: str
    project_id: str
    job_id: str
    trigger: str  # schedule | manual | event
    started_at: str
    ended_at: str = ""
    status: str = "running"  # running | success | failed | skipped
    output_excerpt: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "output_excerpt": self.output_excerpt,
            "error": self.error,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
