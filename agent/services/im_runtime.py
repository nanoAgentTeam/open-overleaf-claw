import asyncio
import hashlib
import json
from typing import Dict, Optional, Any
from loguru import logger
from bus.queue import MessageBus
from channels.base import BaseChannel
from channels.feishu import FeishuChannel
from channels.im_telegram import ImTelegramChannel
from channels.im_qq import ImQQChannel
from channels.im_dingtalk import ImDingTalkChannel
from config.loader import get_config_service
from config.schema import ChannelAccount

class IMRuntimeManager:
    """Manages the lifecycle of active IM channel adapters."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(IMRuntimeManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, bus: Optional[MessageBus] = None):
        if self._initialized:
            return
        self.bus = bus or MessageBus()
        self.active_channels: Dict[str, BaseChannel] = {}
        self._account_hashes: Dict[str, str] = {}
        self._config_service = get_config_service()
        self._initialized = True
        self._running_tasks: Dict[str, asyncio.Task] = {}

    def _migrate_legacy_channels(self, config) -> list:
        """
        Build ChannelAccount entries from legacy channels config (channels.feishu/telegram)
        when im.accounts is empty, ensuring backward compatibility.
        """
        migrated = []
        if config.channels.feishu.enabled and config.channels.feishu.app_id:
            migrated.append(ChannelAccount(
                id="legacy_feishu",
                platform="feishu",
                enabled=True,
                credentials={
                    "app_id": config.channels.feishu.app_id,
                    "app_secret": config.channels.feishu.app_secret,
                },
            ))
        if config.channels.telegram.enabled and config.channels.telegram.token:
            migrated.append(ChannelAccount(
                id="legacy_telegram",
                platform="telegram",
                enabled=True,
                credentials={
                    "token": config.channels.telegram.token,
                },
            ))
        if config.channels.dingtalk.enabled and config.channels.dingtalk.client_id:
            migrated.append(ChannelAccount(
                id="legacy_dingtalk",
                platform="dingtalk",
                enabled=True,
                credentials={
                    "client_id": config.channels.dingtalk.client_id,
                    "client_secret": config.channels.dingtalk.client_secret,
                    "robot_code": config.channels.dingtalk.robot_code,
                    "corp_id": config.channels.dingtalk.corp_id,
                    "agent_id": config.channels.dingtalk.agent_id,
                },
            ))
        return migrated

    async def sync_with_config(self):
        """
        Synchronize active channels with current configuration.
        Starts newly enabled accounts and stops disabled or removed ones.
        Falls back to legacy channels config if im.accounts is empty.
        """
        config = self._config_service.config
        accounts = config.channel.accounts

        # Fallback: migrate legacy channels config when no new-style accounts exist
        if not accounts:
            accounts = self._migrate_legacy_channels(config)
            if accounts:
                logger.info(f"Migrated {len(accounts)} legacy channel(s) to ChannelAccount format")

        # Start all enabled channels
        target_ids = {acc.id for acc in accounts if acc.enabled}

        current_ids = set(self.active_channels.keys())

        # 1. Stop channels that are no longer targeted (disabled, removed, or no longer active)
        for acc_id in list(current_ids):
            if acc_id not in target_ids:
                await self.stop_channel(acc_id)

        # 2. Start or Update channels
        for acc in accounts:
            if acc.id not in target_ids:
                continue

            # Calculate config hash to detect changes
            acc_hash = hashlib.md5(json.dumps(acc.model_dump(), sort_keys=True).encode()).hexdigest()

            # Only restart if config changed
            if acc.id in self.active_channels:
                if self._account_hashes.get(acc.id) == acc_hash:
                    continue
                await self.stop_channel(acc.id)

            self._account_hashes[acc.id] = acc_hash
            await self.start_channel(acc)

    async def start_channel(self, account: ChannelAccount):
        """Initialize and start a specific IM channel."""
        logger.info(f"Starting IM channel: {account.platform} (ID: {account.id})")

        channel: Optional[BaseChannel] = None
        if account.platform == "feishu":
            from config.schema import FeishuConfig
            cfg = FeishuConfig(
                enabled=True,
                app_id=account.credentials.get("app_id", ""),
                app_secret=account.credentials.get("app_secret", ""),
            )
            channel = FeishuChannel(cfg, self.bus)
        elif account.platform == "telegram":
            from config.schema import Config, TelegramConfig
            cfg = Config()
            cfg.channels.telegram = TelegramConfig(
                enabled=True,
                token=account.credentials.get("token", ""),
            )
            channel = ImTelegramChannel(cfg, self.bus)
        elif account.platform == "qq":
            from config.schema import Config, QQConfig
            cfg = Config()
            # Debug: log the credentials we're trying to use
            logger.debug(f"QQ credentials from account: {account.credentials}")
            # Merge QQ credentials into config for ImQQChannel
            # Note: credentials are converted to snake_case during config loading
            cfg.channels.qq = QQConfig(
                enabled=True,
                app_id=account.credentials.get("app_id", ""),
                app_secret=account.credentials.get("app_secret", ""),
                allow_from=[]
            )
            logger.debug(f"QQ config after merge: app_id={cfg.channels.qq.app_id}, app_secret={'*' * len(cfg.channels.qq.app_secret) if cfg.channels.qq.app_secret else 'empty'}")
            channel = ImQQChannel(cfg, self.bus)
        elif account.platform == "dingtalk":
            from config.schema import Config, DingTalkConfig
            cfg = Config()
            logger.debug(f"DingTalk credentials from account: {account.credentials}")
            cfg.channels.dingtalk = DingTalkConfig(
                enabled=True,
                client_id=account.credentials.get("client_id", account.credentials.get("clientId", "")),
                client_secret=account.credentials.get("client_secret", account.credentials.get("clientSecret", "")),
                robot_code=account.credentials.get("robot_code", account.credentials.get("robotCode", "")),
                corp_id=account.credentials.get("corp_id", account.credentials.get("corpId", "")),
                agent_id=account.credentials.get("agent_id", account.credentials.get("agentId", "")),
                allow_from=[],
            )
            channel = ImDingTalkChannel(cfg, self.bus)
        else:
            logger.warning(f"Unsupported platform: {account.platform}")
            return

        if channel:
            self.active_channels[account.id] = channel
            # Start the channel runner as a background task
            task = asyncio.create_task(channel.start())
            self._running_tasks[account.id] = task

            # Subscribe to outbound bus
            self.bus.subscribe_outbound(channel.name, channel.send)
            if account.platform == "telegram":
                # Backward-compatible alias used by notify subscriptions.
                self.bus.subscribe_outbound("telegram", channel.send)
            logger.success(f"IM channel {account.id} ({account.platform}) initialized")

    async def stop_channel(self, account_id: str):
        """Stop and remove a running channel."""
        if account_id in self.active_channels:
            logger.info(f"Stopping IM channel: {account_id}")
            channel = self.active_channels[account_id]

            # Unsubscribe from the bus BEFORE stopping to prevent
            # dispatching to a half-dead channel during shutdown.
            self.bus.unsubscribe_outbound(channel.name, channel.send)
            # Also remove the backward-compatible "telegram" alias if present
            if channel.name != "telegram":
                self.bus.unsubscribe_outbound("telegram", channel.send)

            await channel.stop()

            if account_id in self._running_tasks:
                self._running_tasks[account_id].cancel()
                del self._running_tasks[account_id]

            del self.active_channels[account_id]
            self._account_hashes.pop(account_id, None)

    async def start_all(self):
        """Start all enabled channels and the bus dispatcher."""
        await self.sync_with_config()
        # Ensure the bus is dispatching
        asyncio.create_task(self.bus.dispatch_outbound())

def get_im_runtime(bus: Optional[MessageBus] = None) -> IMRuntimeManager:
    return IMRuntimeManager(bus)
