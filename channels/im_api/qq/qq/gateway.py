import asyncio
import aiohttp
import json
import logging
from .models import WSPayload

logger = logging.getLogger("qq.gateway")

class QQBotGateway:
    def __init__(self, api):
        self.api = api
        self.ws = None
        self.last_seq = None
        self.session_id = None
        self.heartbeat_task = None

    async def start(self, event_handler):
        """启动 Gateway 连接"""
        token = await self.api.get_access_token()

        async with aiohttp.ClientSession() as session:
            # 获取 Gateway URL
            async with session.get(f"{self.api.base_url}/gateway", headers={"Authorization": f"QQBot {token}"}) as resp:
                data = await resp.json()
                url = data["url"]

            logger.info(f"Connecting to {url}")
            async with session.ws_connect(url) as ws:
                self.ws = ws
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        payload = WSPayload(**data)
                        await self._handle_payload(payload, event_handler)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

    async def _handle_payload(self, payload, handler):
        if payload.s is not None:
            self.last_seq = payload.s

        if payload.op == 10: # Hello
            interval = payload.d["heartbeat_interval"] / 1000
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
            await self._identify()
        elif payload.op == 11: # Heartbeat ACK
            logger.debug("Heartbeat ACK received")
        elif payload.op == 0: # Dispatch
            if payload.t == "READY":
                self.session_id = payload.d["session_id"]
                logger.info(f"Connected! Session ID: {self.session_id}")
            # 调用外部处理器
            await handler(payload.t, payload.d)

    async def _identify(self):
        token = await self.api.get_access_token()
        # 默认订阅 C2C, 群聊和频道消息
        intents = (1 << 25) | (1 << 30) | (1 << 0)
        await self.ws.send_json({
            "op": 2,
            "d": {
                "token": f"QQBot {token}",
                "intents": intents,
                "shard": [0, 1]
            }
        })

    async def _heartbeat_loop(self, interval):
        while True:
            await asyncio.sleep(interval)
            if self.ws and not self.ws.closed:
                await self.ws.send_json({"op": 1, "d": self.last_seq})
                logger.debug("Heartbeat sent")
