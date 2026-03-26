"""Tool registry for dynamic tool management."""

from __future__ import annotations
from typing import Any, Optional, Protocol, runtime_checkable, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from core.project import Project
    from core.session import Session

@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    async def execute(self, **kwargs) -> str: ...
    def to_schema(self) -> dict[str, Any]: ...


class ToolRegistry:
    """Registry for agent tools with per-project blacklist filtering."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._project: Optional["Project"] = None

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def bind_context(self, project: "Project") -> None:
        """Bind project context for blacklist filtering."""
        self._project = project

    def _is_authorized(self, tool: Tool) -> bool:
        """Authorization check using per-project blacklist."""
        if not self._project:
            return True

        blacklist = getattr(self._project.config, 'tools_blacklist', [])
        if getattr(tool, '_name', tool.name) in blacklist:
            return False

        return True

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions in OpenAI format, filtered by blacklist."""
        definitions = []
        for tool in self._tools.values():
            if not self._is_authorized(tool):
                continue
            definitions.append(tool.to_schema())
        return definitions

    async def execute(self, name: str, params: dict[str, Any]) -> tuple[str, str]:
        """
        Execute a tool by name with given parameters.
        Returns (result, warning).
        """
        tool = self._tools.get(name)
        if not tool:
            return f"[ERROR] Tool '{name}' not found", ""

        try:
            if hasattr(tool, 'validate_and_execute'):
                return await tool.validate_and_execute(**params)

            import inspect
            import asyncio
            # 同步 execute() 会阻塞事件循环，导致健康检查等无法响应
            # 使用 asyncio.to_thread() 将同步调用卸载到线程池
            if inspect.iscoroutinefunction(tool.execute):
                result = await tool.execute(**params)
            else:
                result = await asyncio.to_thread(tool.execute, **params)
            return result, ""
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return f"[ERROR] executing {name}: {str(e)}", ""

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def get_all_instances(self) -> list[Tool]:
        """Get all registered tool instances."""
        return list(self._tools.values())

    def rebind(self, session: "Session", project: "Project" = None) -> None:
        """Update all tools' session/project references after project switch."""
        if project:
            self._project = project
        for tool in self._tools.values():
            if hasattr(tool, 'session'):
                tool.session = session
            if hasattr(tool, 'project'):
                tool.project = session.project
