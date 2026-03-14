"""Service protocols (interfaces) for the agent framework.

Defines the contracts that decouple AgentLoop from its subsystems:
CommandHandler, CommandResult, CommandContext, and service protocols.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable, Optional, Callable, Awaitable
from pathlib import Path


# ---------------------------------------------------------------------------
# Command system
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    """Result of a command execution."""
    response: Optional[str] = None
    should_continue: bool = False       # True = fall through to LLM processing
    modified_message: Optional[str] = None  # Rewritten message content for LLM
    subagent: Any = None  # 非 None 时 CLI 进入子会话循环


@dataclass
class CommandContext:
    """Immutable context passed to command handlers."""
    chat_id: str = ""
    channel: str = ""
    sender_id: str = ""
    mode: str = "CHAT"
    project_id: str = "Default"
    session_id: str = "default"
    role_name: str = "Assistant"
    role_type: str = "Assistant"

    # Service references (injected by AgentLoop before dispatch)
    publish_chunk: Optional[Callable[[str], None]] = field(default=None, repr=False)
    publish_outbound: Optional[Callable[..., Awaitable]] = field(default=None, repr=False)


@runtime_checkable
class CommandHandler(Protocol):
    """Protocol for a single command handler."""

    async def execute(
        self,
        args: str,
        ctx: CommandContext,
    ) -> CommandResult:
        """Execute the command with given args and context."""
        ...


# ---------------------------------------------------------------------------
# Service protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class StateManagerProtocol(Protocol):
    """Protocol for workflow state management."""

    @property
    def project_id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def research_id(self) -> Optional[str]: ...

    @property
    def task_id(self) -> Optional[str]: ...

    @property
    def workspace(self) -> Path: ...

    @property
    def metadata_root(self) -> Path: ...

    @property
    def session_root(self) -> Path: ...

    @property
    def project_root(self) -> Path: ...
