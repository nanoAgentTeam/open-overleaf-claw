"""DingTalk bot dispatcher."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

from .api import DingTalkAPI
from .context import Context
from .gateway import DingTalkGateway

logger = logging.getLogger("dingtalk.bot")


class DingTalkBot:
    def __init__(self, client_id: str, client_secret: str, robot_code: str = ""):
        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required")

        self.client_id = client_id
        self.client_secret = client_secret
        self.robot_code = robot_code or client_id

        self.api = DingTalkAPI(client_id, client_secret, self.robot_code)
        self.gateway = DingTalkGateway(client_id, client_secret)
        self._handlers: list[Callable[[Context], Awaitable[None]]] = []

    def on_message(self):
        def decorator(func: Callable[[Context], Awaitable[None]]):
            self._handlers.append(func)
            return func

        return decorator

    async def _dispatch(self, payload: dict) -> None:
        ctx = Context(payload, self.api)
        for handler in self._handlers:
            try:
                await handler(ctx)
            except Exception as exc:
                logger.error("DingTalk handler error: %s", exc, exc_info=True)

    async def _on_gateway_event(self, payload: dict, _message_id: str | None, ack=None) -> None:
        await self._dispatch(payload)
        if ack:
            ack(True)

    async def handle_event(self, payload: dict | str) -> None:
        data = payload
        if isinstance(payload, str):
            data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("payload must be a dict or json string")
        await self._dispatch(data)

    async def start(self) -> None:
        logger.info("Starting DingTalk bot")
        await self.gateway.start(self._on_gateway_event)

    async def stop(self) -> None:
        await self.gateway.stop()

    def run(self) -> None:
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            logger.info("DingTalk bot stopped by user")
