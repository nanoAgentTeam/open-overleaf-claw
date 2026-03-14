"""
数据库管理模块（已精简）

原有的 chat_sessions / chat_messages 表已随桌面宠物 Chat 服务移除。
保留 DatabaseManager 骨架以备后续扩展。
"""

import sqlite3
import threading
from typing import List, Dict, Any, Optional


class DatabaseManager:
    """数据库管理器（单例）"""

    _instance = None
    _local = threading.local()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn'):
            from core.infra.config import Config
            self._local.conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
