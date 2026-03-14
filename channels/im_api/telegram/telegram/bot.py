"""Telegram bot core dispatcher."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from telegram import Update

from .api import TelegramBotAPI
from .context import Context
from .gateway import TelegramBotGateway

logger = logging.getLogger("telegram.bot")


class TelegramBot:
    def __init__(self, token: str):
        if not token:
            raise ValueError("token is required")

        self.token = token
        self.api = TelegramBotAPI(token)
        self.gateway = TelegramBotGateway(token)
        self._handlers: list[Callable[[Context], Awaitable[None]]] = []

    @property
    def app(self):
        return self.gateway.app

    def on_message(self):
        def decorator(func: Callable[[Context], Awaitable[None]]):
            self._handlers.append(func)
            return func

        return decorator

    async def _dispatch_event(self, update: Update) -> None:
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user

        if self.gateway.app:
            self.api.set_bot(self.gateway.app.bot)

        content_parts: list[str] = []
        media_paths: list[str] = []

        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        media_file = None
        media_type = None

        if message.photo:
            media_file = message.photo[-1]
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.video:
            media_file = message.video
            media_type = "video"
        elif message.document:
            media_file = message.document
            media_type = "file"

        if media_file and media_type:
            file_id = getattr(media_file, "file_id", "")
            mime_type = getattr(media_file, "mime_type", None)
            if file_id:
                try:
                    path = await self.api.download_file(
                        file_id=file_id,
                        media_type=media_type,
                        mime_type=mime_type,
                    )
                    media_paths.append(path)
                    content_parts.append(f"[{media_type}: {path}]")
                except Exception as exc:
                    logger.error("Telegram media download failed: %s", exc)
                    content_parts.append(f"[{media_type}: download failed]")

        content = "\n".join(part for part in content_parts if part) or "[empty message]"

        # Extract reply/quote info
        reply_to = message.reply_to_message
        reply_content = None
        reply_sender = None
        if reply_to:
            reply_content = reply_to.text or reply_to.caption or ""
            if reply_to.from_user:
                reply_sender = reply_to.from_user.first_name or reply_to.from_user.username or str(reply_to.from_user.id)

        payload = {
            "content": content,
            "message_id": message.message_id,
            "chat_id": message.chat_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "is_private": message.chat.type == "private",
            "media_paths": media_paths,
            "reply_to_content": reply_content,
            "reply_to_sender": reply_sender,
        }

        ctx = Context(payload, self.api)

        for handler in self._handlers:
            try:
                await handler(ctx)
            except Exception as exc:
                logger.error("Telegram handler error: %s", exc, exc_info=True)

    async def start(self) -> None:
        logger.info("Starting Telegram bot")
        await self.gateway.start(self._dispatch_event)

    async def stop(self) -> None:
        await self.gateway.stop()

    def run(self) -> None:
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            logger.info("Telegram bot stopped by user")
