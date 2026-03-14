import os
import asyncio
import logging
from typing import List, Callable, Awaitable
from .api import QQBotAPI
from .gateway import QQBotGateway
from .context import Context

logger = logging.getLogger("qq.bot")

class QQBot:
    """
    QQ 机器人核心类，负责插件注册和事件分发
    """
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv("APP_ID")
        self.client_secret = app_secret or os.getenv("APP_SECRET")

        if not self.app_id or not self.client_secret:
            raise ValueError("APP_ID and APP_SECRET must be provided or set in environment variables")

        self._handlers: List[Callable[[Context], Awaitable[None]]] = []
        self._api = QQBotAPI(self.app_id, self.client_secret)
        self._gateway = QQBotGateway(self._api)

    def on_message(self):
        """
        装饰器：注册一个消息处理插件
        """
        def decorator(func: Callable[[Context], Awaitable[None]]):
            self._handlers.append(func)
            return func
        return decorator

    async def _dispatch_event(self, event_type: str, data: dict):
        """
        内部方法：将网关事件转换为 Context 并分发给所有插件
        """
        # 仅处理消息相关的事件
        if event_type not in ["C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"]:
            return

        ctx = Context(event_type, data, self._api)

        for handler in self._handlers:
            try:
                await handler(ctx)
            except Exception as e:
                logger.error(f"Plugin handler error: {e}", exc_info=True)

    async def start(self):
        """
        异步启动机器人
        """
        logger.info("Starting QQ Bot...")
        await self._gateway.start(self._dispatch_event)

    def run(self):
        """
        同步运行入口
        """
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
