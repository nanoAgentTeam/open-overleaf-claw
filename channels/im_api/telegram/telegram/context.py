"""Telegram inbound context."""

from __future__ import annotations

from .api import TelegramBotAPI


class Context:
    def __init__(self, payload: dict, api: TelegramBotAPI):
        self.raw = payload
        self._api = api

        self.content = str(payload.get("content") or "").strip()
        self.msg_id = str(payload.get("message_id") or "")
        self.user_id = str(payload.get("user_id") or "")
        self.group_id = None if bool(payload.get("is_private", True)) else str(payload.get("chat_id") or "")
        self.chat_id = str(payload.get("chat_id") or "")
        self.is_private = bool(payload.get("is_private", True))
        self.username = str(payload.get("username") or "")
        self.first_name = str(payload.get("first_name") or "")
        self.attachments = list(payload.get("media_paths") or [])
        self.reply_to_content = str(payload.get("reply_to_content") or "")
        self.reply_to_sender = str(payload.get("reply_to_sender") or "")

    async def reply(self, content: str) -> dict:
        if not content:
            return {"ok": False, "error": "empty content"}

        return await self._api.send_message(
            chat_id=self.chat_id,
            content=content,
            reply_to_message_id=self.msg_id or None,
        )

    async def reply_image(self, path_or_url: str, caption: str = "") -> dict:
        return await self._api.send_photo(
            chat_id=self.chat_id,
            photo=path_or_url,
            caption=caption,
            reply_to_message_id=self.msg_id or None,
        )
