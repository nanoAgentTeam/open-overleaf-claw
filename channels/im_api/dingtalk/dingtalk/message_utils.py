"""Message parsing helpers adapted from the TS DingTalk plugin."""

from __future__ import annotations

import re

from .types import ParsedMessage, as_dict


def detect_markdown_and_extract_title(
    text: str,
    options: dict | None,
    default_title: str,
) -> tuple[bool, str]:
    opts = options or {}
    has_markdown = bool(re.search(r"^[#*>-]|[*_`#[\]]", text)) or "\n" in text
    use_markdown = bool(opts.get("use_markdown", opts.get("useMarkdown", has_markdown)))

    raw_title = str(opts.get("title") or "").strip()
    if not raw_title and use_markdown:
        first_line = text.split("\n", 1)[0]
        raw_title = re.sub(r"^[#*\s\->]+", "", first_line).strip()[:20]

    return use_markdown, raw_title or default_title


def extract_message_content(data: dict) -> dict:
    msgtype = str(data.get("msgtype") or "text")

    if msgtype == "text":
        text = str((data.get("text") or {}).get("content") or "").strip()
        return as_dict(ParsedMessage(text=text, message_type="text"))

    if msgtype == "richText":
        rich = ((data.get("content") or {}).get("richText") or [])
        text_parts: list[str] = []
        picture_download_code: str | None = None

        for part in rich:
            ptype = part.get("type")
            if (ptype in (None, "text")) and part.get("text"):
                text_parts.append(str(part["text"]))
            if ptype == "at" and part.get("atName"):
                text_parts.append(f"@{part['atName']} ")
            if ptype == "picture" and part.get("downloadCode") and not picture_download_code:
                picture_download_code = str(part["downloadCode"])

        text = "".join(text_parts).strip() or ("<media:image>" if picture_download_code else "[richText]")
        return as_dict(
            ParsedMessage(
                text=text,
                message_type="richText",
                media_code=picture_download_code,
                media_type="image" if picture_download_code else None,
            )
        )

    if msgtype == "picture":
        return as_dict(
            ParsedMessage(
                text="<media:image>",
                message_type="picture",
                media_code=((data.get("content") or {}).get("downloadCode")),
                media_type="image",
            )
        )

    if msgtype == "audio":
        content = data.get("content") or {}
        text = str(content.get("recognition") or "<media:voice>")
        return as_dict(
            ParsedMessage(
                text=text,
                message_type="audio",
                media_code=content.get("downloadCode"),
                media_type="audio",
            )
        )

    if msgtype == "video":
        return as_dict(
            ParsedMessage(
                text="<media:video>",
                message_type="video",
                media_code=((data.get("content") or {}).get("downloadCode")),
                media_type="video",
            )
        )

    if msgtype == "file":
        content = data.get("content") or {}
        name = str(content.get("fileName") or "file")
        return as_dict(
            ParsedMessage(
                text=f"<media:file> ({name})",
                message_type="file",
                media_code=content.get("downloadCode"),
                media_type="file",
            )
        )

    text = str((data.get("text") or {}).get("content") or "").strip() or f"[{msgtype}]"
    return as_dict(ParsedMessage(text=text, message_type=msgtype))
