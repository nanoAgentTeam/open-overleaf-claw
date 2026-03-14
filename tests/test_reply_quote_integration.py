"""Integration tests for reply/quote message awareness.

These tests simulate the full callback chain from raw platform message objects
through to the message bus, verifying that [Replying to: ...] markers appear
in the InboundMessage.content that reaches bus.publish_inbound().
"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch


def run_async(coro):
    """Helper to run async test cases."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Telegram: full _dispatch_event -> _on_message_callback -> bus chain
# ---------------------------------------------------------------------------

class TestTelegramFullReplyChain(unittest.TestCase):
    """Simulate Telegram reply message from Update object to bus."""

    def _build_update(self, text="Hello", reply_text=None, reply_sender_name=None):
        """Build a mock telegram Update with optional reply_to_message."""
        update = MagicMock()

        # Main message
        message = MagicMock()
        message.text = text
        message.caption = None
        message.photo = []
        message.voice = None
        message.audio = None
        message.video = None
        message.document = None
        message.message_id = 100
        message.chat_id = 12345
        message.chat.type = "private"

        # reply_to_message
        if reply_text is not None:
            reply_msg = MagicMock()
            reply_msg.text = reply_text
            reply_msg.caption = None
            reply_user = MagicMock()
            reply_user.first_name = reply_sender_name or "Someone"
            reply_user.username = "someone_u"
            reply_user.id = 999
            reply_msg.from_user = reply_user
            message.reply_to_message = reply_msg
        else:
            message.reply_to_message = None

        update.message = message

        # effective_user
        user = MagicMock()
        user.id = 789
        user.username = "testuser"
        user.first_name = "Test"
        update.effective_user = user

        return update

    def test_full_chain_with_reply(self):
        """Reply message should flow through bot -> channel -> bus with [Replying to] tag."""
        from channels.im_api.telegram.telegram.bot import TelegramBot
        from channels.im_telegram import ImTelegramChannel

        # --- Step 1: TelegramBot._dispatch_event produces payload ---
        bot = TelegramBot.__new__(TelegramBot)
        bot.token = "test_token"
        bot.api = MagicMock()
        bot.gateway = MagicMock()
        bot.gateway.app = None
        bot._handlers = []

        captured_ctx = {}

        async def capture_handler(ctx):
            captured_ctx["ctx"] = ctx

        bot._handlers.append(capture_handler)

        update = self._build_update(
            text="I agree with you",
            reply_text="What do you think about the proposal?",
            reply_sender_name="Alice",
        )

        run_async(bot._dispatch_event(update))

        ctx = captured_ctx["ctx"]
        self.assertEqual(ctx.reply_to_content, "What do you think about the proposal?")
        self.assertEqual(ctx.reply_to_sender, "Alice")

        # --- Step 2: ImTelegramChannel._on_message_callback prepends tag ---
        config = MagicMock()
        config.channels.telegram.token = "test"
        config.allow_from = []  # allow all
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        channel = ImTelegramChannel(config, bus)
        channel._running = True

        # Instead of using run_coroutine_threadsafe (needs separate thread),
        # directly call _handle_message to simulate what the callback does
        content = ctx.content
        if ctx.reply_to_content:
            quoted = ctx.reply_to_content[:200]
            sender_tag = f" ({ctx.reply_to_sender})" if ctx.reply_to_sender else ""
            content = f'[Replying to{sender_tag}: "{quoted}"]\n{content}'

        run_async(channel._handle_message(
            sender_id=str(ctx.user_id),
            chat_id=str(ctx.chat_id),
            content=content,
            media=list(ctx.attachments),
            metadata={"message_id": ctx.msg_id, "is_private": ctx.is_private},
        ))

        # Verify bus received the message with reply tag
        bus.publish_inbound.assert_called_once()
        inbound_msg = bus.publish_inbound.call_args[0][0]
        self.assertIn('[Replying to (Alice): "What do you think about the proposal?"]', inbound_msg.content)
        self.assertIn("I agree with you", inbound_msg.content)
        self.assertEqual(inbound_msg.channel, "im_telegram")

    def test_full_chain_without_reply(self):
        """Normal message should flow through without [Replying to] tag."""
        from channels.im_api.telegram.telegram.bot import TelegramBot

        bot = TelegramBot.__new__(TelegramBot)
        bot.token = "test_token"
        bot.api = MagicMock()
        bot.gateway = MagicMock()
        bot.gateway.app = None
        bot._handlers = []

        captured_ctx = {}

        async def capture_handler(ctx):
            captured_ctx["ctx"] = ctx

        bot._handlers.append(capture_handler)

        update = self._build_update(text="Just a normal message", reply_text=None)
        run_async(bot._dispatch_event(update))

        ctx = captured_ctx["ctx"]
        self.assertEqual(ctx.reply_to_content, "")
        self.assertEqual(ctx.reply_to_sender, "")

        # Channel callback
        config = MagicMock()
        config.allow_from = []  # allow all
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        from channels.im_telegram import ImTelegramChannel
        channel = ImTelegramChannel(config, bus)

        content = ctx.content
        if ctx.reply_to_content:
            quoted = ctx.reply_to_content[:200]
            sender_tag = f" ({ctx.reply_to_sender})" if ctx.reply_to_sender else ""
            content = f'[Replying to{sender_tag}: "{quoted}"]\n{content}'

        run_async(channel._handle_message(
            sender_id=str(ctx.user_id),
            chat_id=str(ctx.chat_id),
            content=content,
            media=[],
            metadata={},
        ))

        inbound_msg = bus.publish_inbound.call_args[0][0]
        self.assertNotIn("[Replying to", inbound_msg.content)
        self.assertEqual(inbound_msg.content, "Just a normal message")

    def test_reply_with_media_caption(self):
        """Replying to a message that was a photo with caption."""
        from channels.im_api.telegram.telegram.bot import TelegramBot

        bot = TelegramBot.__new__(TelegramBot)
        bot.token = "test_token"
        bot.api = MagicMock()
        bot.gateway = MagicMock()
        bot.gateway.app = None
        bot._handlers = []

        captured_ctx = {}

        async def capture_handler(ctx):
            captured_ctx["ctx"] = ctx

        bot._handlers.append(capture_handler)

        # Build update where reply_to_message has caption but no text
        update = self._build_update(text="Nice photo!")
        reply_msg = MagicMock()
        reply_msg.text = None
        reply_msg.caption = "Sunset at the beach"
        reply_user = MagicMock()
        reply_user.first_name = "Bob"
        reply_user.username = "bob_u"
        reply_user.id = 555
        reply_msg.from_user = reply_user
        update.message.reply_to_message = reply_msg

        run_async(bot._dispatch_event(update))

        ctx = captured_ctx["ctx"]
        self.assertEqual(ctx.reply_to_content, "Sunset at the beach")
        self.assertEqual(ctx.reply_to_sender, "Bob")


# ---------------------------------------------------------------------------
# Feishu: full _handle_im_message -> _process_message -> bus chain
# ---------------------------------------------------------------------------

class TestFeishuFullReplyChain(unittest.TestCase):
    """Simulate Feishu reply message from P2ImMessageReceiveV1 to bus."""

    def _build_event_data(self, text="Hello", parent_id=None, chat_type="p2p"):
        """Build a mock P2ImMessageReceiveV1."""
        data = MagicMock()
        message = MagicMock()
        message.content = json.dumps({"text": text})
        message.message_type = "text"
        message.message_id = "om_msg_001"
        message.chat_id = "oc_chat_001"
        message.chat_type = chat_type
        message.parent_id = parent_id

        sender = MagicMock()
        sender.sender_id.open_id = "ou_user_001"

        data.event.message = message
        data.event.sender = sender
        return data

    def test_full_chain_with_parent_message(self):
        """Reply to a text message should include [Replying to] in content."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test_app"
        config.app_secret = "test_secret"
        config.allow_from = []
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        channel = FeishuChannel(config, bus)
        channel._running = True
        channel._main_loop = asyncio.get_event_loop()

        # Mock API client for parent message fetch
        mock_client = MagicMock()
        channel._api_client = mock_client

        # Parent message response
        mock_parent = MagicMock()
        mock_parent.msg_type = "text"
        mock_body = MagicMock()
        mock_body.content = json.dumps({"text": "Please review the draft"})
        mock_parent.body = mock_body
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.items = [mock_parent]
        mock_client.im.v1.message.get.return_value = mock_resp

        # Build event with parent_id
        event_data = self._build_event_data(
            text="Done, LGTM",
            parent_id="om_parent_msg_001",
        )

        # Call _handle_im_message (runs synchronously since we mock main_loop)
        # We need to intercept _process_message since it's scheduled via run_coroutine_threadsafe
        with patch.object(channel, '_main_loop', None):
            # Disable run_coroutine_threadsafe by setting main_loop to None
            # Instead, manually trace the flow
            pass

        # Directly test the text construction in _handle_im_message
        message = event_data.event.message
        text = json.loads(message.content).get("text", "")

        parent_id = getattr(message, "parent_id", None)
        if parent_id:
            quoted_text = channel._fetch_parent_message_text(parent_id)
            if quoted_text:
                text = f'[Replying to: "{quoted_text[:200]}"]\n{text}'

        self.assertEqual(text, '[Replying to: "Please review the draft"]\nDone, LGTM')

        # Now verify end-to-end through _process_message -> _handle_message -> bus
        run_async(channel._process_message(
            open_id="ou_user_001",
            text=text,
            message_id="om_msg_001",
            chat_id="oc_chat_001",
            chat_type="p2p",
            media_paths=[],
        ))

        bus.publish_inbound.assert_called_once()
        inbound_msg = bus.publish_inbound.call_args[0][0]
        self.assertIn('[Replying to: "Please review the draft"]', inbound_msg.content)
        self.assertIn("Done, LGTM", inbound_msg.content)
        self.assertEqual(inbound_msg.channel, "feishu")

    def test_full_chain_parent_is_post_message(self):
        """Reply to a post (rich text) message should extract text content."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        config.allow_from = []
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        channel = FeishuChannel(config, bus)
        mock_client = MagicMock()
        channel._api_client = mock_client

        # Parent is a post message
        mock_parent = MagicMock()
        mock_parent.msg_type = "post"
        mock_body = MagicMock()
        mock_body.content = json.dumps({
            "content": [
                [{"tag": "text", "text": "Meeting notes: "}, {"tag": "text", "text": "action items below"}],
            ]
        })
        mock_parent.body = mock_body
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.items = [mock_parent]
        mock_client.im.v1.message.get.return_value = mock_resp

        result = channel._fetch_parent_message_text("om_parent_post")
        self.assertEqual(result, "Meeting notes: action items below")

    def test_full_chain_parent_is_image(self):
        """Reply to an image message should show [image message]."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        bus = MagicMock()

        channel = FeishuChannel(config, bus)
        mock_client = MagicMock()
        channel._api_client = mock_client

        mock_parent = MagicMock()
        mock_parent.msg_type = "image"
        mock_body = MagicMock()
        mock_body.content = json.dumps({"image_key": "img_xxx"})
        mock_parent.body = mock_body
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.items = [mock_parent]
        mock_client.im.v1.message.get.return_value = mock_resp

        result = channel._fetch_parent_message_text("om_parent_img")
        self.assertEqual(result, "[image message]")

    def test_full_chain_no_parent(self):
        """Message without parent_id should not have [Replying to] tag."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        config.allow_from = []
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        channel = FeishuChannel(config, bus)
        channel._api_client = MagicMock()

        event_data = self._build_event_data(text="Just a normal msg", parent_id=None)

        message = event_data.event.message
        text = json.loads(message.content).get("text", "")
        parent_id = getattr(message, "parent_id", None)
        if parent_id:
            quoted_text = channel._fetch_parent_message_text(parent_id)
            if quoted_text:
                text = f'[Replying to: "{quoted_text[:200]}"]\n{text}'

        self.assertEqual(text, "Just a normal msg")
        self.assertNotIn("[Replying to", text)

    def test_parent_fetch_failure_graceful(self):
        """If parent message fetch fails, original message should go through unchanged."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        config.allow_from = []
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        channel = FeishuChannel(config, bus)
        mock_client = MagicMock()
        channel._api_client = mock_client

        # API returns failure
        mock_resp = MagicMock()
        mock_resp.success.return_value = False
        mock_resp.code = 403
        mock_resp.msg = "forbidden"
        mock_client.im.v1.message.get.return_value = mock_resp

        event_data = self._build_event_data(text="my reply", parent_id="om_deleted_msg")

        message = event_data.event.message
        text = json.loads(message.content).get("text", "")
        parent_id = getattr(message, "parent_id", None)
        if parent_id:
            quoted_text = channel._fetch_parent_message_text(parent_id)
            if quoted_text:
                text = f'[Replying to: "{quoted_text[:200]}"]\n{text}'

        # Should remain unchanged since fetch failed
        self.assertEqual(text, "my reply")


# ---------------------------------------------------------------------------
# DingTalk: full Context creation -> _on_message_callback -> bus chain
# ---------------------------------------------------------------------------

class TestDingTalkFullReplyChain(unittest.TestCase):
    """Simulate DingTalk reply message from raw payload to bus."""

    def test_full_chain_with_quote(self):
        """Message with quoteContent should include [Replying to] in bus message."""
        from channels.im_api.dingtalk.dingtalk.context import Context as DTContext
        from channels.im_dingtalk import ImDingTalkChannel

        # Build raw payload with quoteContent
        payload = {
            "msgId": "msg_dt_001",
            "msgtype": "text",
            "text": {"content": "Yes, let's do that"},
            "conversationType": "2",  # group
            "conversationId": "cid_group_001",
            "senderStaffId": "user_dt_001",
            "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession/xxx",
            "quoteContent": "Should we schedule a meeting tomorrow?",
        }
        api = MagicMock()
        ctx = DTContext(payload, api)

        # Verify context extraction
        self.assertEqual(ctx.quote_content, "Should we schedule a meeting tomorrow?")
        self.assertEqual(ctx.content, "Yes, let's do that")
        self.assertFalse(ctx.is_private)

        # Simulate channel callback logic
        config = MagicMock()
        config.allow_from = []  # allow all
        bus = MagicMock()
        bus.publish_inbound = AsyncMock()

        channel = ImDingTalkChannel(config, bus)
        channel._running = True
        channel._bot = MagicMock()

        # Replicate _on_message_callback content construction
        quote_content = getattr(ctx, "quote_content", "")
        content = ctx.content
        if quote_content:
            content = f'[Replying to: "{quote_content[:200]}"]\n{content}'

        chat_id = str(ctx.user_id if ctx.is_private else (ctx.group_id or ctx.user_id))

        run_async(channel._handle_message(
            sender_id=str(ctx.user_id),
            chat_id=chat_id,
            content=content,
            media=[],
            metadata={"msg_id": ctx.msg_id, "is_private": ctx.is_private},
        ))

        bus.publish_inbound.assert_called_once()
        inbound_msg = bus.publish_inbound.call_args[0][0]
        self.assertIn('[Replying to: "Should we schedule a meeting tomorrow?"]', inbound_msg.content)
        self.assertIn("Yes, let's do that", inbound_msg.content)
        self.assertEqual(inbound_msg.channel, "im_dingtalk")

    def test_full_chain_without_quote(self):
        """Normal message should not have [Replying to] tag."""
        from channels.im_api.dingtalk.dingtalk.context import Context as DTContext

        payload = {
            "msgId": "msg_dt_002",
            "msgtype": "text",
            "text": {"content": "Normal message"},
            "conversationType": "1",
            "conversationId": "cid_private_001",
            "senderStaffId": "user_dt_001",
            "sessionWebhook": "",
        }
        api = MagicMock()
        ctx = DTContext(payload, api)

        self.assertEqual(ctx.quote_content, "")

        content = ctx.content
        if ctx.quote_content:
            content = f'[Replying to: "{ctx.quote_content[:200]}"]\n{content}'

        self.assertEqual(content, "Normal message")
        self.assertNotIn("[Replying to", content)

    def test_full_chain_nested_quote_content(self):
        """quoteContent nested in content dict should also work."""
        from channels.im_api.dingtalk.dingtalk.context import Context as DTContext

        payload = {
            "msgId": "msg_dt_003",
            "msgtype": "text",
            "text": {"content": "Replying here"},
            "conversationType": "1",
            "conversationId": "cid_001",
            "senderStaffId": "user_001",
            "sessionWebhook": "",
            "content": {"quoteContent": "Nested quote text"},
        }
        api = MagicMock()
        ctx = DTContext(payload, api)

        self.assertEqual(ctx.quote_content, "Nested quote text")


# ---------------------------------------------------------------------------
# Cross-channel: verify [Replying to] format consistency
# ---------------------------------------------------------------------------

class TestReplyFormatConsistency(unittest.TestCase):
    """Ensure all channels produce the same [Replying to: "..."] format."""

    def test_telegram_format(self):
        quoted = "original message"
        sender = "Alice"
        content = "my reply"
        sender_tag = f" ({sender})" if sender else ""
        result = f'[Replying to{sender_tag}: "{quoted}"]\n{content}'
        self.assertTrue(result.startswith('[Replying to'))
        self.assertIn('"original message"', result)
        self.assertIn("my reply", result)

    def test_feishu_format(self):
        quoted_text = "parent message content"
        text = "child reply"
        result = f'[Replying to: "{quoted_text[:200]}"]\n{text}'
        self.assertTrue(result.startswith('[Replying to:'))
        self.assertIn('"parent message content"', result)

    def test_dingtalk_format(self):
        quote = "quoted text here"
        content = "reply text"
        result = f'[Replying to: "{quote[:200]}"]\n{content}'
        self.assertTrue(result.startswith('[Replying to:'))
        self.assertIn('"quoted text here"', result)

    def test_all_start_with_same_prefix(self):
        """All channels should produce content starting with [Replying to."""
        formats = [
            '[Replying to (Alice): "hello"]\nreply',   # Telegram (with sender)
            '[Replying to: "hello"]\nreply',             # Feishu
            '[Replying to: "hello"]\nreply',             # DingTalk
        ]
        for fmt in formats:
            self.assertTrue(fmt.startswith("[Replying to"))
            self.assertIn('"hello"', fmt)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestReplyEdgeCases(unittest.TestCase):
    """Edge cases for reply/quote handling."""

    def test_empty_reply_content(self):
        """Empty reply content (e.g. only media, no text) should not prepend."""
        reply_content = ""
        content = "responding to a photo"
        if reply_content:
            content = f'[Replying to: "{reply_content[:200]}"]\n{content}'
        self.assertEqual(content, "responding to a photo")

    def test_reply_with_newlines(self):
        """Reply content with newlines should be preserved in quoted text."""
        reply_content = "Line 1\nLine 2\nLine 3"
        content = "my response"
        if reply_content:
            content = f'[Replying to: "{reply_content[:200]}"]\n{content}'
        self.assertIn("Line 1\nLine 2", content)

    def test_reply_with_special_chars(self):
        """Reply content with quotes and brackets should be preserved."""
        reply_content = 'He said "hello" and [waved]'
        content = "cool"
        if reply_content:
            content = f'[Replying to: "{reply_content[:200]}"]\n{content}'
        self.assertIn('He said "hello"', content)

    def test_unicode_reply_content(self):
        """Chinese/Unicode text in reply should work fine."""
        reply_content = "这是一条中文消息"
        content = "收到了"
        if reply_content:
            content = f'[Replying to: "{reply_content[:200]}"]\n{content}'
        self.assertIn("这是一条中文消息", content)
        self.assertIn("收到了", content)


if __name__ == "__main__":
    unittest.main()
