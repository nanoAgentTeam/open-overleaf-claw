import aiohttp
import time
import logging
import base64
import os
from typing import Optional, Any

logger = logging.getLogger("qq.api")

class QQBotAPI:
    def __init__(self, app_id: str, client_secret: str):
        self.app_id = app_id
        self.client_secret = client_secret
        self.base_url = "https://api.sgroup.qq.com"
        self.token_url = "https://bots.qq.com/app/getAppAccessToken"
        self._cached_token = None
        self._expires_at = 0

    async def get_access_token(self) -> str:
        """获取并缓存 AccessToken"""
        if self._cached_token and time.time() < self._expires_at - 300:
            return self._cached_token

        payload = {"appId": self.app_id, "clientSecret": self.client_secret}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Failed to get token: {text}")
                data = await resp.json()
                self._cached_token = data["access_token"]
                self._expires_at = time.time() + int(data.get("expires_in", 7200))
                logger.info("Token refreshed")
                return self._cached_token

    async def request(self, method: str, path: str, json_data: Optional[Any] = None):
        """通用 API 请求封装"""
        token = await self.get_access_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json"
        }
        # Log the request details for debugging
        logger.info(f"API Request: {method} {path}, data: {json_data}")
        async with aiohttp.ClientSession() as session:
            async with session.request(method, f"{self.base_url}{path}", headers=headers, json=json_data) as resp:
                data = await resp.json()
                if not resp.ok:
                    logger.error(f"API Error [{path}]: {data}")
                else:
                    logger.info(f"API Success [{path}]")
                return data

    async def send_c2c_message(self, openid: str, content: str, msg_id: str = None):
        """发送私聊消息"""
        payload = {
            "content": content,
            "msg_type": 0,
        }
        if msg_id:
            payload["msg_id"] = msg_id
        return await self.request("POST", f"/v2/users/{openid}/messages", payload)

    async def send_group_message(self, group_openid: str, content: str, msg_id: str = None):
        """发送群聊消息"""
        payload = {
            "content": content,
            "msg_type": 0,
        }
        if msg_id:
            payload["msg_id"] = msg_id
        return await self.request("POST", f"/v2/groups/{group_openid}/messages", payload)

    async def upload_media(self, openid: str, file_type: int, url: str = None, file_data: str = None, is_group: bool = False, file_name: str = None):
        """上传富媒体文件到腾讯服务器"""
        path = f"/v2/{'groups' if is_group else 'users'}/{openid}/files"
        payload = {"file_type": file_type, "srv_send_msg": False}
        if url: payload["url"] = url
        if file_data: payload["file_data"] = file_data
        if file_name: payload["file_name"] = file_name
        return await self.request("POST", path, payload)

    async def send_image(self, openid: str, image_path_or_url: str, msg_id: str, is_group: bool = False):
        """发送图片：自动处理本地路径或网络 URL"""
        return await self._send_rich_media(openid, image_path_or_url, file_type=1, msg_id=msg_id, is_group=is_group)

    async def send_file(self, openid: str, file_path_or_url: str, msg_id: str, is_group: bool = False):
        """发送文件（PDF、文档等）：自动处理本地路径或网络 URL"""
        return await self._send_rich_media(openid, file_path_or_url, file_type=4, msg_id=msg_id, is_group=is_group)

    async def send_video(self, openid: str, video_path_or_url: str, msg_id: str, is_group: bool = False):
        """发送视频"""
        return await self._send_rich_media(openid, video_path_or_url, file_type=2, msg_id=msg_id, is_group=is_group)

    async def _send_rich_media(self, openid: str, path_or_url: str, file_type: int, msg_id: str, is_group: bool = False):
        """通用富媒体发送：file_type 1=图片 2=视频 4=文件"""
        file_data = None

        if path_or_url.startswith(("http://", "https://")):
            async with aiohttp.ClientSession() as session:
                async with session.get(path_or_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"下载文件失败: {resp.status}")
                    content = await resp.read()
                    file_data = base64.b64encode(content).decode()
        else:
            if os.path.exists(path_or_url):
                with open(path_or_url, "rb") as f:
                    file_data = base64.b64encode(f.read()).decode()
            else:
                raise FileNotFoundError(f"文件未找到: {path_or_url}")

        # 从路径中提取文件名，让 QQ 正确显示文件名和后缀
        file_name = os.path.basename(path_or_url)
        res = await self.upload_media(openid, file_type, file_data=file_data, is_group=is_group, file_name=file_name)
        file_info = res.get("file_info")
        if not file_info:
            raise Exception(f"上传文件失败，未获取到 file_info: {res}")

        path = f"/v2/{'groups' if is_group else 'users'}/{openid}/messages"
        return await self.request("POST", path, {
            "msg_type": 7,
            "media": {"file_info": file_info},
            "msg_id": msg_id
        })
