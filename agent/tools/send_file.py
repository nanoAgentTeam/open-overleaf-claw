"""Tool for sending files (PDF, images, etc.) back to the user via the message bus."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from bus.events import OutboundMessage
from core.tools.base import BaseTool


class SendFileTool(BaseTool):
    """Channel-agnostic file sending tool.

    The agent calls this tool with a file path; the tool publishes an
    ``OutboundMessage`` with the ``media`` field populated.  The active
    channel (Telegram, DingTalk, Feishu, QQ, …) handles the actual
    delivery in its own ``send()`` implementation.

    When running in automation/CLI mode (channel="cli"), the tool falls
    back to sending via global push subscriptions (Telegram Bot API, etc.)
    so that files actually reach the user.
    """

    def __init__(self, tool_context: Any):
        self.bus = getattr(tool_context, "bus", None)
        self.session = getattr(tool_context, "session", None)
        self.project = getattr(tool_context, "project", None)
        self.config = getattr(tool_context, "config", None)
        self.workspace = getattr(tool_context, "workspace", None)

    @property
    def name(self) -> str:
        return "send_file"

    @property
    def description(self) -> str:
        return (
            "Send a file (PDF, image, document, etc.) to the user in the current chat. "
            "Provide the file path relative to the workspace (or absolute). "
            "Optionally include a caption message."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to send (relative to workspace or absolute).",
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption / message to accompany the file.",
                    "default": "",
                },
            },
            "required": ["file_path"],
        }

    def _resolve_path(self, file_path: str) -> Optional[Path]:
        """Resolve *file_path* to an absolute ``Path``, checking existence."""
        p = Path(file_path)
        if p.is_absolute():
            return p if p.is_file() else None

        # Try session workspace first
        if self.session:
            try:
                resolved = self.session.resolve(file_path)
                if resolved.is_file():
                    return resolved
            except Exception:
                pass

        # Try project core directory
        if self.project:
            candidate = self.project.core / file_path
            if candidate.is_file():
                return candidate
            candidate = self.project.root / file_path
            if candidate.is_file():
                return candidate

        # Fallback: workspace
        if self.workspace:
            candidate = Path(self.workspace) / file_path
            if candidate.is_file():
                return candidate

        return None

    def _collect_push_targets(self) -> List[Dict[str, str]]:
        """Collect Telegram push targets from global pushSubscriptions."""
        targets: List[Dict[str, str]] = []
        if not self.config:
            return targets
        try:
            global_items = list(
                getattr(getattr(self.config, "push_subscriptions", None), "items", []) or []
            )
            for item in global_items:
                if not bool(getattr(item, "enabled", True)):
                    continue
                channel = str(getattr(item, "channel", "") or "").strip().lower()
                if channel != "telegram":
                    continue
                params = getattr(item, "params", {}) or {}
                bot_token = str(params.get("bot_token") or params.get("token") or "").strip()
                chat_id = str(params.get("chat_id") or getattr(item, "chat_id", "") or "").strip()
                if bot_token and chat_id:
                    targets.append({"bot_token": bot_token, "chat_id": chat_id})
        except Exception as e:
            logger.warning(f"send_file: failed to collect push targets: {e}")
        return targets

    @staticmethod
    def _send_telegram_file_sync(bot_token: str, chat_id: str, file_path: Path, caption: str = "") -> None:
        """Send a file via Telegram Bot API (sendDocument) synchronously."""
        import http.client
        import mimetypes
        import uuid

        boundary = uuid.uuid4().hex
        url = f"/bot{bot_token}/sendDocument"

        parts: list[bytes] = []
        # chat_id field
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}".encode())
        # caption field
        if caption:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}".encode())
        # document file field
        mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        file_data = file_path.read_bytes()
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{file_path.name}\"\r\n"
            f"Content-Type: {mime_type}\r\n\r\n".encode() + file_data
        )
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"\r\n".join(parts)

        conn = http.client.HTTPSConnection("api.telegram.org", timeout=30)
        try:
            conn.request("POST", url, body=body, headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            })
            resp = conn.getresponse()
            resp_body = resp.read().decode("utf-8", errors="ignore")
            if resp.status != 200:
                raise RuntimeError(f"Telegram API returned {resp.status}: {resp_body[:300]}")
        finally:
            conn.close()

    async def execute(
        self,
        file_path: str,
        caption: str = "",
        message_context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        if not self.bus:
            return "[ERROR] send_file requires message bus (not available outside gateway mode)."

        if not message_context:
            return "[ERROR] send_file requires message context (chat_id / channel)."

        chat_id = message_context.get("chat_id")
        channel = message_context.get("channel")
        if not chat_id or not channel:
            return "[ERROR] send_file: missing chat_id or channel in message context."

        resolved = self._resolve_path(file_path)
        if not resolved:
            return f"[ERROR] File not found: {file_path}"

        file_size = resolved.stat().st_size
        if file_size == 0:
            return f"[ERROR] File is empty: {file_path}"

        size_mb = file_size / (1024 * 1024)
        if size_mb > 50:
            return f"[ERROR] File too large ({size_mb:.1f}MB). Most platforms limit files to 50MB."

        # Automation/CLI mode: channel is "cli", bus has no real subscriber.
        # Fall back to sending via Telegram Bot API using global push subscriptions.
        if channel == "cli":
            targets = self._collect_push_targets()
            if not targets:
                return (
                    "[ERROR] send_file: running in automation mode but no Telegram push "
                    "subscription configured in settings.json. Cannot deliver file."
                )
            sent = 0
            for target in targets:
                try:
                    await asyncio.to_thread(
                        self._send_telegram_file_sync,
                        target["bot_token"], target["chat_id"],
                        resolved, caption,
                    )
                    sent += 1
                except Exception as e:
                    logger.warning(f"send_file: Telegram push failed for {target['chat_id']}: {e}")
            if sent == 0:
                return f"[ERROR] send_file: failed to deliver {resolved.name} to all targets."
            logger.info(f"send_file: pushed {resolved.name} ({size_mb:.2f}MB) to {sent} Telegram target(s)")
            return f"File sent: {resolved.name} ({size_mb:.2f}MB) to {sent} recipient(s)"

        # Normal interactive mode: publish to bus for active channel to handle
        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=caption,
            media=[str(resolved)],
            metadata={"source": "send_file"},
        )
        try:
            await self.bus.publish_outbound(msg)
        except Exception as exc:
            logger.error(f"send_file publish failed: {exc}")
            return f"[ERROR] Failed to send file: {exc}"

        logger.info(f"send_file: queued {resolved.name} ({size_mb:.2f}MB) to {channel}:{chat_id}")
        return f"✅ File successfully sent to user: {resolved.name} ({size_mb:.2f}MB)"
