"""Rich-based terminal renderer for structured agent events."""

from __future__ import annotations

import json
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from agent.memory.trace import AgentEvent, EventType


class TerminalRenderer:
    """Renders structured AgentEvents to the terminal using Rich components.

    For LLM streaming tokens, falls back to raw sys.stdout.write
    (Rich Panels require complete content).
    """

    def __init__(self, console: Optional[Console] = None, verbose: bool = False):
        self.console = console or Console(stderr=False)
        self.verbose = verbose
        self._in_stream = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_event(self, event: AgentEvent) -> None:
        """Main dispatch: render an event to the terminal."""
        handler = {
            EventType.STEP_START: self._render_step_start,
            EventType.TOOL_CALL: self._render_tool_call,
            EventType.TOOL_RESULT: self._render_tool_result,
            EventType.TOKEN: self._render_token,
            EventType.LLM_END: self._render_llm_end,
            EventType.SUBAGENT_START: self._render_subagent_start,
            EventType.SUBAGENT_END: self._render_subagent_end,
            EventType.WORKER_LOG: self._render_worker_log,
            EventType.TASK_UPDATE: self._render_task_update,
            EventType.TURN_END: self._render_turn_end,
            EventType.WARNING: self._render_warning,
            EventType.ERROR: self._render_error,
        }.get(event.type)

        if handler:
            handler(event)

    def on_token(self, token: str) -> None:
        """Raw token callback for LLM streaming (sys.stdout passthrough)."""
        if not self._in_stream:
            self._in_stream = True
        sys.stdout.write(token)
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Internal renderers
    # ------------------------------------------------------------------

    def _end_stream(self) -> None:
        """Flush a trailing newline if we were mid-stream."""
        if self._in_stream:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._in_stream = False

    def _render_step_start(self, event: AgentEvent) -> None:
        self._end_stream()
        iteration = event.iteration or 0
        max_iter = event.max_iterations or 0
        remaining = max_iter - iteration

        if remaining <= 5:
            style = "bold red"
            label = f"Step {iteration}/{max_iter}  ({remaining} remaining)"
        else:
            style = "dim cyan"
            label = f"Step {iteration}/{max_iter}  ({remaining} remaining)"

        self.console.print(
            Panel(label, style=style, width=50, padding=(0, 1))
        )

    def _render_tool_call(self, event: AgentEvent) -> None:
        self._end_stream()
        name = event.tool_name or "unknown"
        args = event.tool_args or {}

        if name == "assign_task":
            agent = args.get("agent_name", "subagent")
            self.console.print(
                Panel(
                    f"[bold]{agent}[/bold] working...",
                    title="Subagent",
                    style="magenta",
                    width=60,
                    padding=(0, 1),
                )
            )
        elif name == "create_subagent":
            agent = args.get("name", "agent")
            self.console.print(f"  [dim magenta]create[/dim magenta] subagent '{agent}'")
        elif "search" in name:
            query = args.get("query", "...")
            self.console.print(f"  [dim cyan]search[/dim cyan] {name}('{query}')")
        else:
            args_str = json.dumps(args, ensure_ascii=False)
            if len(args_str) > 80:
                args_str = args_str[:80] + "..."
            self.console.print(f"  [dim green]tool[/dim green]   {name}({args_str})")

    # Display tuning
    DEFAULT_RESULT_PREVIEW_CHARS = 1200
    VERBOSE_RESULT_PREVIEW_CHARS = 4000
    FULL_TOOL_PANEL_MAX_CHARS = 8000

    # Tools whose results should be shown in full-style panel by default
    _FULL_DISPLAY_TOOLS = {
        "task_propose",
        "task_build",
        "task_modify",
        "task_execute",
        "task_commit",
        "read_file",
        "bash",
    }

    def _render_tool_result(self, event: AgentEvent) -> None:
        name = event.tool_name or ""
        output = event.data.get("output", "")
        warning = event.data.get("warning", "")
        full_display = name in self._FULL_DISPLAY_TOOLS

        if self.verbose or full_display:
            max_len = self.FULL_TOOL_PANEL_MAX_CHARS if full_display else self.VERBOSE_RESULT_PREVIEW_CHARS
            truncated = len(output) > max_len
            display = output if not truncated else output[:max_len] + "\n... [truncated]"
            title = f"Result: {name}"
            if truncated:
                title += f" ({len(output)} chars, showing {max_len})"
            self.console.print(
                Panel(display, title=title, style="dim", width=100)
            )
        else:
            max_len = self.DEFAULT_RESULT_PREVIEW_CHARS
            truncated = len(output) > max_len
            display = output if not truncated else output[:max_len] + "..."
            suffix = "" if not truncated else f" [truncated {len(output)}→{max_len}]"
            self.console.print(f"  [dim]result[/dim]  {name} -> {display}{suffix}")

        if warning:
            self.console.print(f"  [yellow]warning: {warning}[/yellow]")

    def _render_token(self, event: AgentEvent) -> None:
        token = event.data.get("token", "")
        if token:
            self.on_token(token)

    def _render_llm_end(self, event: AgentEvent) -> None:
        self._end_stream()
        if self.verbose and event.token_usage:
            u = event.token_usage
            self.console.print(
                f"  [dim]tokens: prompt={u.get('prompt_tokens', '?')} "
                f"completion={u.get('completion_tokens', '?')}[/dim]"
            )

    def _render_subagent_start(self, event: AgentEvent) -> None:
        self._end_stream()
        role = event.role or "subagent"
        self.console.print(
            Panel(f"[bold]{role}[/bold] started", title="Subagent", style="magenta", width=50, padding=(0, 1))
        )

    def _render_subagent_end(self, event: AgentEvent) -> None:
        role = event.role or "subagent"
        self.console.print(f"  [magenta]subagent[/magenta] {role} finished")

    def _render_worker_log(self, event: AgentEvent) -> None:
        msg = event.data.get("message", "")
        role = event.role or "worker"
        self.console.print(f"  [dim blue][{role}][/dim blue] {msg}")

    def _render_task_update(self, event: AgentEvent) -> None:
        msg = event.data.get("message", "")
        self.console.print(f"  [bold blue]task[/bold blue] {msg}")

    def _render_turn_end(self, event: AgentEvent) -> None:
        self._end_stream()
        duration = event.duration_ms
        if duration is not None:
            secs = duration / 1000
            self.console.print(f"\n[dim]Turn completed in {secs:.1f}s[/dim]")

    def _render_warning(self, event: AgentEvent) -> None:
        msg = event.data.get("message", "")
        self.console.print(f"[yellow]warning: {msg}[/yellow]")

    def _render_error(self, event: AgentEvent) -> None:
        msg = event.data.get("error", event.data.get("message", ""))
        self.console.print(f"[bold red]error: {msg}[/bold red]")
