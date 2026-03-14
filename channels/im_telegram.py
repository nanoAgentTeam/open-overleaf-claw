"""Telegram channel implementation using the local im_api package."""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from typing import Any, Optional

from loguru import logger

from bus.events import OutboundMessage
from bus.queue import MessageBus
from channels.base import BaseChannel
from config.schema import Config


class ImTelegramChannel(BaseChannel):
    """Telegram channel adapter following the same style as `ImQQChannel`."""

    name = "im_telegram"

    def __init__(self, config: Config, bus: MessageBus):
        super().__init__(config, bus)
        self.config = config
        self._bot = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bot_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._message_buffers: dict[str, str] = {}
        self._chat_context: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        if self._bot_thread and self._bot_thread.is_alive():
            logger.warning("IM Telegram channel is already running")
            return

        token = self.config.channels.telegram.token or os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_TOKEN", "")

        if not token:
            logger.error("Telegram bot token not configured")
            return

        logger.info("Starting IM Telegram channel")
        self._running = True

        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running event loop found")

        try:
            from channels.im_api.telegram.telegram.bot import TelegramBot

            self._bot = TelegramBot(token=token)
            self._bot.on_message()(self._on_message_callback)

            def run_bot() -> None:
                try:
                    loop = asyncio.new_event_loop()
                    self._bot_loop = loop
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._bot.start())
                except Exception as exc:
                    logger.error(f"Telegram bot error: {exc}")
                finally:
                    self._bot_loop = None

            self._bot_thread = threading.Thread(target=run_bot, daemon=True)
            self._bot_thread.start()
            logger.info("IM Telegram channel started")
        except ImportError as exc:
            logger.error(f"Failed to import Telegram module: {exc}")
            self._running = False
        except Exception as exc:
            logger.error(f"Failed to start Telegram channel: {exc}")
            self._running = False

    async def stop(self) -> None:
        self._running = False
        bot_loop = self._bot_loop  # snapshot before clearing

        if self._bot and bot_loop and bot_loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._bot.stop(), bot_loop)
                fut.result(timeout=10)
            except concurrent.futures.TimeoutError:
                logger.warning("Telegram bot stop timed out, forcing loop shutdown")
                bot_loop.call_soon_threadsafe(bot_loop.stop)
            except Exception as exc:
                logger.warning(f"Telegram stop warning: {exc}")
        elif self._bot:
            try:
                await self._bot.stop()
            except Exception as exc:
                logger.warning(f"Telegram stop warning: {exc}")

        if self._bot_thread and self._bot_thread.is_alive():
            await asyncio.to_thread(self._bot_thread.join, 5)
            if self._bot_thread.is_alive():
                logger.warning("Telegram bot thread did not exit cleanly")

        self._bot = None
        self._bot_loop = None
        self._bot_thread = None
        self._message_buffers.clear()
        self._chat_context.clear()
        logger.info("IM Telegram channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        if not self._bot:
            logger.warning("Telegram bot is not initialized")
            return

        chat_id = msg.chat_id

        try:
            if msg.is_chunk:
                self._message_buffers[chat_id] = self._message_buffers.get(chat_id, "") + msg.content
                return

            final_content = msg.content or ""
            if chat_id in self._message_buffers:
                buffered = self._message_buffers.pop(chat_id)
                if buffered:
                    final_content = buffered

            metadata = msg.metadata or {}
            cached_ctx = self._chat_context.get(chat_id, {})
            reply_to_message_id = (
                metadata.get("reply_to_message_id")
                or metadata.get("message_id")
                or cached_ctx.get("message_id")
            )

            from channels.im_api.telegram.telegram.api import TelegramBotAPI

            bot_instance = self._bot.api.bot if self._bot and self._bot.api else None
            api = TelegramBotAPI(token=self._bot.token, bot=bot_instance)

            # Send media files (documents, images, videos)
            for media_path in (msg.media or []):
                try:
                    await self._send_media_file(api, chat_id, media_path, reply_to_message_id)
                except Exception as exc:
                    logger.error(f"Error sending media {media_path}: {exc}")

            if final_content.strip():
                await api.send_message(
                    chat_id=chat_id,
                    content=final_content,
                    reply_to_message_id=reply_to_message_id,
                )
                logger.info(f"Telegram sent to {chat_id}: {final_content[:100]}...")
        except Exception as exc:
            logger.error(f"Error sending Telegram message: {exc}")

    @staticmethod
    async def _send_media_file(
        api: "TelegramBotAPI",
        chat_id: str,
        media_path: str,
        reply_to_message_id: Any = None,
    ) -> None:
        """Dispatch a media file to the appropriate Telegram send method."""
        from pathlib import Path

        lower = media_path.lower()
        is_url = lower.startswith(("http://", "https://"))
        if is_url:
            url_path = lower.split("?")[0].split("/")[-1]
            ext = ("." + url_path.rsplit(".", 1)[-1]) if "." in url_path else ""
        else:
            ext = Path(media_path).suffix.lower()

        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv"}

        if ext in image_exts:
            await api.send_photo(chat_id=chat_id, photo=media_path, reply_to_message_id=reply_to_message_id)
        elif ext in video_exts:
            await api.send_video(chat_id=chat_id, video=media_path, reply_to_message_id=reply_to_message_id)
        else:
            await api.send_document(chat_id=chat_id, document=media_path, reply_to_message_id=reply_to_message_id)

        logger.info(f"Telegram media sent to {chat_id}: {media_path}")

    async def _on_message_callback(self, ctx) -> None:
        try:
            chat_id = str(ctx.chat_id)
            sender_id = str(ctx.user_id or "unknown")
            metadata = {
                "message_id": ctx.msg_id,
                "user_id": ctx.user_id,
                "username": ctx.username,
                "first_name": ctx.first_name,
                "is_private": ctx.is_private,
            }

            self._chat_context[chat_id] = metadata

            # Prepend reply/quote context if present
            content = ctx.content
            if ctx.reply_to_content:
                quoted = ctx.reply_to_content[:200]
                sender_tag = f" ({ctx.reply_to_sender})" if ctx.reply_to_sender else ""
                content = f"[Replying to{sender_tag}: \"{quoted}\"]\n{content}"

            if self._main_loop and self._main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._handle_message(
                        sender_id=sender_id,
                        chat_id=chat_id,
                        content=content,
                        media=list(ctx.attachments),
                        metadata=metadata,
                    ),
                    self._main_loop,
                )
            else:
                logger.warning("Main event loop not available, Telegram message dropped")
        except Exception as exc:
            logger.error(f"Error in Telegram callback: {exc}")
