"""Access token cache for DingTalk API."""

from __future__ import annotations

import asyncio
import time

import httpx


class DingTalkAuth:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get_access_token(self, client_id: str, client_secret: str) -> str:
        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required")

        key = client_id
        now = time.time()
        cached = self._cache.get(key)
        if cached and cached[1] > now + 60:
            return cached[0]

        async with self._lock:
            cached = self._cache.get(key)
            now = time.time()
            if cached and cached[1] > now + 60:
                return cached[0]

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                    json={"appKey": client_id, "appSecret": client_secret},
                )
            resp.raise_for_status()
            payload = resp.json()

            token = str(payload.get("accessToken") or "")
            expire_in = int(payload.get("expireIn") or 7200)
            if not token:
                raise RuntimeError(f"Invalid token payload: {payload}")

            self._cache[key] = (token, time.time() + expire_in)
            return token


auth_client = DingTalkAuth()
