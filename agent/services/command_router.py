"""Registry-based command router.

Replaces the if/elif chain in AgentLoop._process_message() (lines 518-705)
with a config-driven dispatch system backed by commands.json.
"""

from __future__ import annotations
from typing import Optional
from loguru import logger

from config.registry import ConfigRegistry, CommandDef
from agent.services.protocols import CommandHandler, CommandContext, CommandResult


class CommandRouter:
    """
    Routes slash commands to their handlers using commands.json config.

    Usage:
        router = CommandRouter(config_registry)
        result = await router.dispatch("/deepresearch transformers", ctx)
        if result is None:
            # Not a command, fall through to LLM
        elif result.should_continue:
            # Command rewrote the message, continue to LLM with result.modified_message
        else:
            # Command fully handled, return result.response
    """

    def __init__(self, registry: ConfigRegistry):
        self._registry = registry
        self._handlers: dict[str, CommandHandler] = {}
        self._aliases: dict[str, str] = {}
        self._build_alias_map()

    def _build_alias_map(self) -> None:
        """Pre-build alias -> canonical name mapping."""
        for name, cmd_def in self._registry.get_all_commands().items():
            for alias in cmd_def.aliases:
                self._aliases[alias] = name

    def register_handler(self, command_name: str, handler: CommandHandler) -> None:
        """Register a handler for a command name."""
        self._handlers[command_name] = handler

    def resolve_command(self, text: str) -> tuple[Optional[CommandDef], str]:
        """Parse input text and return (command_def, args_string) or (None, '')."""
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None, ""

        parts = stripped.split(None, 1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Resolve alias
        canonical = self._aliases.get(cmd_name, cmd_name)
        cmd_def = self._registry.get_command(canonical)

        return cmd_def, args

    async def dispatch(
        self,
        text: str,
        ctx: CommandContext,
    ) -> Optional[CommandResult]:
        """
        Attempt to dispatch a command.
        Returns None if text is not a recognized command.
        Returns CommandResult if handled.
        """
        cmd_def, args = self.resolve_command(text)
        if cmd_def is None:
            return None

        if cmd_def.requires_args and not args.strip():
            return CommandResult(
                response=f"Usage: {cmd_def.args_usage or cmd_def.name + ' <args>'}"
            )

        handler = self._handlers.get(cmd_def.name)
        if handler is None:
            logger.warning(f"Command {cmd_def.name} has no registered handler")
            return None

        try:
            return await handler.execute(args, ctx)
        except Exception as e:
            logger.error(f"Command {cmd_def.name} failed: {e}")
            return CommandResult(response=f"Command failed: {e}")
