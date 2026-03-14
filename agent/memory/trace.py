"""Structured event tracing for agent loops.

Provides:
- EventType enum and AgentEvent dataclass for structured event emission
- TraceLogger for real-time JSONL event streaming and trajectory enhancement
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventType(str, Enum):
    """Types of events emitted by the agent loop."""
    STEP_START = "step_start"
    LLM_START = "llm_start"
    TOKEN = "token"
    LLM_END = "llm_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_END = "subagent_end"
    WORKER_LOG = "worker_log"
    TASK_UPDATE = "task_update"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class AgentEvent:
    """Single structured event emitted by the agent loop."""
    type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    data: dict[str, Any] = field(default_factory=dict)
    iteration: Optional[int] = None
    max_iterations: Optional[int] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_id: Optional[str] = None
    duration_ms: Optional[float] = None
    token_usage: Optional[dict[str, int]] = None
    role: Optional[str] = None


class TraceLogger:
    """Real-time JSONL event stream writer and per-turn trajectory enhancer.

    Two responsibilities:
    1. Append every AgentEvent as one JSON line to a session JSONL file
    2. Accumulate timing/token data to inject into the per-turn trajectory JSON
    """

    def __init__(self, events_dir: Path, session_id: str):
        self.events_dir = events_dir
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id

        # Sanitize session_id for filename (replace / and other unsafe chars)
        safe_id = session_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        self._jsonl_path = self.events_dir / f"events_{safe_id}.jsonl"

        # Per-turn accumulators
        self._turn_start: Optional[float] = None
        self._turn_token_usage: dict[str, int] = {}
        self._step_timings: list[dict[str, Any]] = []
        self._current_step_start: Optional[float] = None

    def emit(self, event: AgentEvent) -> None:
        """Write a single event as one JSON line (append mode, synchronous)."""
        line = json.dumps({
            "type": event.type.value,
            "ts": event.timestamp,
            "iter": event.iteration,
            "tool": event.tool_name,
            "tool_args": event.tool_args,
            "duration_ms": event.duration_ms,
            "tokens": event.token_usage,
            "role": event.role,
            "data": event.data,
        }, ensure_ascii=False)

        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass  # never crash the agent for tracing

    def mark_turn_start(self) -> None:
        """Called at the beginning of _process_message."""
        self._turn_start = time.monotonic()
        self._turn_token_usage = {}
        self._step_timings = []
        self._current_step_start = None

    def mark_step_start(self, iteration: int) -> None:
        self._current_step_start = time.monotonic()

    def mark_step_end(self, iteration: int) -> None:
        if self._current_step_start is not None:
            elapsed = (time.monotonic() - self._current_step_start) * 1000
            self._step_timings.append({
                "iteration": iteration,
                "duration_ms": round(elapsed, 1),
            })
            self._current_step_start = None

    def record_llm_usage(self, usage: dict[str, int]) -> None:
        """Accumulate token usage from an LLM response."""
        for k, v in usage.items():
            self._turn_token_usage[k] = self._turn_token_usage.get(k, 0) + v

    def enhance_trajectory(self, trajectory: dict[str, Any]) -> dict[str, Any]:
        """Inject accumulated timing and token data into the trajectory dict."""
        if self._turn_start is not None:
            trajectory["duration_ms"] = round(
                (time.monotonic() - self._turn_start) * 1000, 1
            )
        if self._turn_token_usage:
            trajectory["token_usage"] = self._turn_token_usage
        if self._step_timings:
            trajectory["step_timings"] = self._step_timings
        return trajectory
