"""DingTalk inbound context."""

from __future__ import annotations

from .api import DingTalkAPI
from .message_utils import extract_message_content


class Context:
    def __init__(self, payload: dict, api: DingTalkAPI):
        self.raw = payload
        self._api = api

        parsed = extract_message_content(payload)
        self.content = parsed["text"]
        self.message_type = parsed["message_type"]
        self.media_code = parsed.get("media_code")
        self.media_type = parsed.get("media_type")

        self.msg_id = str(payload.get("msgId") or "")
        self.event_type = str(payload.get("msgtype") or "")
        self.session_webhook = str(payload.get("sessionWebhook") or "")
        self.conversation_type = str(payload.get("conversationType") or "")
        self.conversation_id = str(payload.get("conversationId") or "")

        self.user_id = str(payload.get("senderStaffId") or payload.get("senderId") or "")
        self.group_id = self.conversation_id if self.conversation_type != "1" else None
        self.is_private = self.conversation_type == "1"

        # Best-effort: extract quoted/reply content from raw payload
        self.quote_content = str(payload.get("quoteContent") or "")
        if not self.quote_content:
            # Some DingTalk versions nest it under content
            self.quote_content = str((payload.get("content") or {}).get("quoteContent") or "")

    async def reply(self, content: str) -> dict:
        if not content:
            return {"ok": False, "error": "empty content"}

        if self.session_webhook:
            return await self._api.send_by_session(self.session_webhook, content, at_user_id=self.user_id if not self.is_private else None)

        target = self.user_id if self.is_private else (self.group_id or self.user_id)
        return await self._api.send_proactive_text(target, content)

    async def reply_image(self, file_path: str) -> dict:
        target = self.user_id if self.is_private else (self.group_id or self.user_id)
        return await self._api.send_proactive_media(target, file_path, media_type="image")
