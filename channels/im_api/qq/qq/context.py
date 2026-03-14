from typing import Dict, Any, Optional

class Context:
    """
    QQ 机器人消息上下文，封装了单次消息的基础接口
    """
    def __init__(self, event_type: str, data: Dict[str, Any], api):
        self.event_type = event_type
        self.raw = data
        self._api = api

        # 基础字段提取
        self.content = data.get("content", "").strip()
        self.msg_id = data.get("id", "")
        self.attachments = data.get("attachments", [])  # 提取附件列表

        # 识别消息来源并设置 user_id / group_id
        if event_type == "C2C_MESSAGE_CREATE":
            self.user_id = data["author"]["user_openid"]
            self.group_id = None
            self.is_private = True
        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            # 群聊中提取发送者 openid 和群 openid
            self.user_id = data["author"].get("member_openid")
            self.group_id = data.get("group_openid")
            self.is_private = False
        else:
            self.user_id = None
            self.group_id = None
            self.is_private = False

    async def reply(self, content: str):
        """
        快速回复接口：自动判断私聊或群聊并发送消息
        """
        if not content:
            return

        if self.is_private:
            return await self._api.send_c2c_message(self.user_id, content, self.msg_id)
        elif self.group_id:
            return await self._api.send_group_message(self.group_id, content, self.msg_id)

    async def reply_image(self, path_or_url: str):
        """
        回复图片：支持本地路径或网络 URL
        """
        target_id = self.group_id if self.group_id else self.user_id
        return await self._api.send_image(target_id, path_or_url, self.msg_id, is_group=not self.is_private)
