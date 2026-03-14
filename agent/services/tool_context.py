"""ToolContext: narrow interface replacing direct AgentLoop access in tools.

Tools receive a ToolContext instead of the entire AgentLoop, keeping coupling
minimal and making dependencies explicit.
"""

from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any, Optional, Set

from loguru import logger


class ToolContext:
    """
    Facade that exposes only the AgentLoop attributes tools actually need.

    Created by AgentLoop and passed to ToolLoader as a replacement for
    the raw ``agent_loop`` reference.  Tools should depend on this class
    (or its attributes) rather than importing AgentLoop directly.
    """

    def __init__(
        self,
        *,
        provider: Any,
        model: str,
        workspace: Path,
        project_id: str,
        session_id: str,
        research_id: Optional[str] = None,
        task_id: Optional[str] = None,
        mode: str = "CHAT",
        role_name: str = "Assistant",
        role_type: str = "Assistant",
        profile: str = "chat_mode_agent",
        bus: Any = None,
        config: Any = None,
        metadata_root: Optional[Path] = None,
        file_root: Optional[Path] = None,
        work_dir: Optional[Path] = None,
        tools: Any = None,
        context_manager: Any = None,
        active_background_tasks: Optional[Set[asyncio.Task]] = None,
        switch_mode_fn: Any = None,
        session: Any = None,
        project: Any = None,
        switch_project_fn: Any = None,
        automation_runtime: Any = None,
    ):
        # [G-M10] Validate required fields
        if session is None:
            logger.warning("ToolContext: no 'session' provided")
        if provider is None:
            raise ValueError("ToolContext requires a non-None 'provider'")
        if workspace is None or not isinstance(workspace, Path):
            raise ValueError("ToolContext requires a valid Path for 'workspace'")

        self.provider = provider
        self.model = model
        self.workspace = workspace
        self.project_id = project_id
        self.session_id = session_id
        self.research_id = research_id
        self.task_id = task_id
        self.mode = mode
        self.role_name = role_name
        self.role_type = role_type
        self.profile = profile
        self.bus = bus
        self.config = config
        self.metadata_root = metadata_root
        self.file_root = file_root
        self.work_dir = work_dir
        self.tools = tools
        self.context_manager = context_manager
        self.active_background_tasks = active_background_tasks or set()
        self._switch_mode_fn = switch_mode_fn
        self.session = session
        self.project = project
        self.switch_project_fn = switch_project_fn
        self.automation_runtime = automation_runtime

    # --- convenience methods ---

    def get_virtual_root(self) -> Path:
        """Return the project core directory."""
        if self.session:
            return self.session.project.core
        return self.file_root or self.workspace

    def register_background_task(self, task: asyncio.Task) -> None:
        """Register a background task for lifecycle management."""
        self.active_background_tasks.add(task)
        task.add_done_callback(self.active_background_tasks.discard)

    async def switch_mode(self, mode: str, **kwargs) -> None:
        """Delegate mode switching back to AgentLoop."""
        if self._switch_mode_fn:
            await self._switch_mode_fn(mode, **kwargs)
        else:
            logger.warning("ToolContext: switch_mode called but no switch_mode_fn bound")
