"""Telegram long-polling gateway."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from telegram import Update
from telegram.error import Conflict
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logger = logging.getLogger("telegram.gateway")

_MAX_CONFLICT_RETRIES = 5
_CONFLICT_BASE_DELAY = 2.0


class TelegramBotGateway:
    def __init__(self, token: str):
        self.token = token
        self.app: Optional[Application] = None
        self._running = False

    async def start(self, event_handler: Callable[[Update], Awaitable[None]]) -> None:
        self.app = Application.builder().token(self.token).build()

        async def _on_message(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
            await event_handler(update)

        self.app.add_handler(
            MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL,
                _on_message,
            )
        )

        logger.info("Starting Telegram bot gateway (polling)")
        await self.app.initialize()
        await self.app.start()

        if self.app.updater:
            await self._start_polling_with_retry()

        self._running = True
        while self._running:
            await asyncio.sleep(1)

    async def _start_polling_with_retry(self) -> None:
        """Start polling with exponential backoff on Conflict errors."""
        delay = _CONFLICT_BASE_DELAY
        for attempt in range(1, _MAX_CONFLICT_RETRIES + 1):
            try:
                await self.app.bot.delete_webhook(drop_pending_updates=True)
                await self.app.updater.start_polling(
                    allowed_updates=["message"],
                    drop_pending_updates=True,
                )
                return
            except Conflict:
                if attempt == _MAX_CONFLICT_RETRIES:
                    logger.error(
                        "Telegram Conflict persists after %d retries, giving up",
                        _MAX_CONFLICT_RETRIES,
                    )
                    raise
                logger.warning(
                    "Telegram Conflict (attempt %d/%d), retrying in %.0fs...",
                    attempt, _MAX_CONFLICT_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                delay *= 2

    async def stop(self) -> None:
        self._running = False

        if not self.app:
            return

        try:
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
        except Exception as exc:
            logger.warning("Telegram updater stop warning: %s", exc)

        try:
            await self.app.stop()
        except Exception as exc:
            logger.warning("Telegram app stop warning: %s", exc)

        try:
            await self.app.shutdown()
        except Exception as exc:
            logger.warning("Telegram app shutdown warning: %s", exc)
