"""
Skill Registry — folder-based skill definition and loading.

Skills live in config/.skills/{skill-name}/SKILL.md with YAML frontmatter.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

# Default location: config/.skills/ relative to project root
_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / ".skills"


class Skill:
    """A single skill loaded from a SKILL.md file."""

    def __init__(self, path: Path):
        self.path = str(path.resolve())   # absolute — agent uses this to resolve relative refs
        self.name: str = ""
        self.description: str = ""
        self.instructions: str = ""       # SKILL.md body without frontmatter
        self.allowed_tools: Optional[List[str]] = None
        self._load(path)

    def _load(self, path: Path) -> None:
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(f"SKILL.md not found in {path}")
        content = skill_md.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml
                meta = yaml.safe_load(parts[1]) or {}
                self.name = meta.get("name", path.name)
                self.description = meta.get("description", "")
                self.allowed_tools = meta.get("allowed-tools")
                self.instructions = parts[2].strip()
            else:
                self.name = path.name
                self.instructions = content
        else:
            self.name = path.name
            self.instructions = content


class SkillRegistry:
    """
    Scans a skills directory and provides lookup by name.

    Args:
        skills_dir: Directory containing skill subdirectories.
        allowed: If given, only load skills whose names are in this list.
                 None means load all discovered skills.
    """

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        allowed: Optional[List[str]] = None,
    ):
        self._dir = Path(skills_dir) if skills_dir else _DEFAULT_SKILLS_DIR
        self._skills: Dict[str, Skill] = {}
        self._load(allowed)

    def _load(self, allowed: Optional[List[str]]) -> None:
        if not self._dir.exists():
            return
        for entry in sorted(self._dir.iterdir()):
            if not entry.is_dir():
                continue
            if allowed is not None and entry.name not in allowed:
                continue
            try:
                skill = Skill(entry)
                if skill.name:
                    self._skills[skill.name] = skill
            except Exception as e:
                logger.warning(f"Failed to load skill at {entry}: {e}")

    # ── public API ────────────────────────────────────────────────────────────

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_names(self) -> List[str]:
        return list(self._skills.keys())

    def get_skills_metadata(self) -> List[Dict[str, str]]:
        """Return [{name, description}, ...] for all loaded skills."""
        return [
            {"name": s.name, "description": s.description}
            for s in self._skills.values()
        ]

    def is_empty(self) -> bool:
        return len(self._skills) == 0
