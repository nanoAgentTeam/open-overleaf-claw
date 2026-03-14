"""Section-based system prompt assembly."""

from __future__ import annotations


class PromptBuilder:
    """Ordered KV section registry for system prompt assembly."""

    def __init__(self):
        self._sections: dict[str, str] = {}  # key → content
        self._order: list[str] = []           # insertion order

    def set(self, key: str, content: str) -> PromptBuilder:
        """Add or replace a section. Preserves insertion order for new keys."""
        if key not in self._sections:
            self._order.append(key)
        self._sections[key] = content
        return self

    def remove(self, key: str) -> PromptBuilder:
        """Remove a section. No-op if key doesn't exist."""
        if key in self._sections:
            del self._sections[key]
            self._order.remove(key)
        return self

    def get(self, key: str) -> str | None:
        """Get a section's content."""
        return self._sections.get(key)

    def has(self, key: str) -> bool:
        return key in self._sections

    def keys(self) -> list[str]:
        """Return section keys in order."""
        return list(self._order)

    def build(self, separator: str = "\n\n") -> str:
        """Concatenate all sections in order, skipping empty content."""
        parts = [self._sections[k] for k in self._order if self._sections.get(k)]
        return separator.join(parts)

    def clear(self) -> None:
        """Remove all sections."""
        self._sections.clear()
        self._order.clear()
