"""Shared type helpers for the DingTalk adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedMessage:
    text: str
    message_type: str
    media_code: str | None = None
    media_type: str | None = None


def as_dict(parsed: ParsedMessage) -> dict[str, Any]:
    return {
        "text": parsed.text,
        "message_type": parsed.message_type,
        "media_code": parsed.media_code,
        "media_type": parsed.media_type,
    }
