"""
Activate Skill Tool

Loads and injects the full SOP of a named skill into the agent's context.
The skill_registry is injected by ToolLoader from the agent context dict.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.tools.base import BaseTool


class ActivateSkillTool(BaseTool):
    """
    Loads and returns the full SOP instructions for a named skill.
    Once activated, the agent MUST follow the skill's protocol for subsequent steps.
    """

    def __init__(self, skill_registry: Optional[Any] = None):
        self._registry = skill_registry

    # ── BaseTool interface ────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "activate_skill"

    @property
    def description(self) -> str:
        if self._registry and not self._registry.is_empty():
            names = ", ".join(f'"{n}"' for n in self._registry.list_names())
        else:
            names = "(none configured)"
        return (
            f"Load the full Standard Operating Procedure (SOP) for a specialized skill. "
            f"Available skills: {names}. "
            f"Call this when your task falls into a domain covered by one of the listed skills."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        available = self._registry.list_names() if self._registry else []
        prop: Dict[str, Any] = {
            "type": "string",
            "description": "Name of the skill to activate.",
        }
        if available:
            prop["enum"] = available
        return {
            "type": "object",
            "properties": {"skill_name": prop},
            "required": ["skill_name"],
        }

    def get_status_message(self, skill_name: str = "", **kwargs) -> str:
        return f"\n\n📖 激活 skill: {skill_name}...\n"

    async def execute(self, skill_name: str) -> str:
        if not self._registry:
            return "Error: skill_registry not initialized. Cannot activate skills."

        skill = self._registry.get_skill(skill_name)
        if not skill:
            available = self._registry.list_names()
            return (
                f"Skill '{skill_name}' not found. "
                f"Available: {available}. "
                f"Please call activate_skill with one of these names."
            )

        return (
            f"--- SKILL ACTIVATED: {skill.name} ---\n"
            f"Skill Base Path: {skill.path}\n\n"
            f"Instructions:\n{skill.instructions}\n\n"
            f"--- END SKILL: {skill.name} ---\n\n"
            f"IMPORTANT:\n"
            f"1. Strictly follow the SOP above for all subsequent steps related to this domain.\n"
            f"2. Any relative file paths mentioned in the instructions (e.g. `./templates/foo.md`, "
            f"`checklists/bar.md`) are relative to the Skill Base Path: {skill.path}\n"
            f"   Resolve them by prepending this base path before reading or referencing them.\n"
            f"3. Use `bash ls {skill.path}` to explore the skill directory and discover "
            f"any referenced resource files."
        )
