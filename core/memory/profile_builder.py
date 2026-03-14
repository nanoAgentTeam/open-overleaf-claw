"""Profile builder protocol for project memory."""

from __future__ import annotations

from typing import Any, Protocol


class ProfileBuilder(Protocol):
    """Build one profile snapshot from project context."""

    name: str

    def build(self, project: Any) -> dict[str, Any]:
        ...
