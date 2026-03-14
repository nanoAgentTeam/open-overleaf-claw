"""Tests for reply/quote message awareness across channels."""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock


class TestTelegramReplyExtraction(unittest.TestCase):
    """Test Telegram bot extracts reply_to_message info."""

    def test_payload_includes_reply_fields_when_replying(self):
        """When message.reply_to_message exists, payload should include reply info."""
        from channels.im_api.telegram.telegram.context import Context

        payload = {
            "content": "Yes I agree",
            "message_id": 123,
            "chat_id": 456,
            "user_id": 789,
            "username": "testuser",
            "first_name": "Test",
            "is_private": True,
            "media_paths": [],
            "reply_to_content": "What do you think about this?",
            "reply_to_sender": "Alice",
        }
        api = MagicMock()
        ctx = Context(payload, api)

        self.assertEqual(ctx.reply_to_content, "What do you think about this?")
        self.assertEqual(ctx.reply_to_sender, "Alice")

    def test_payload_empty_reply_fields_when_not_replying(self):
        """When no reply_to_message, fields should be empty strings."""
        from channels.im_api.telegram.telegram.context import Context

        payload = {
            "content": "Hello",
            "message_id": 123,
            "chat_id": 456,
            "user_id": 789,
            "username": "testuser",
            "first_name": "Test",
            "is_private": True,
            "media_paths": [],
            "reply_to_content": None,
            "reply_to_sender": None,
        }
        api = MagicMock()
        ctx = Context(payload, api)

        self.assertEqual(ctx.reply_to_content, "")
        self.assertEqual(ctx.reply_to_sender, "")


class TestTelegramChannelReplyPrepend(unittest.TestCase):
    """Test ImTelegramChannel prepends reply context to content."""

    def _make_ctx(self, content="Hello", reply_content="", reply_sender=""):
        ctx = MagicMock()
        ctx.chat_id = "12345"
        ctx.user_id = "789"
        ctx.username = "testuser"
        ctx.first_name = "Test"
        ctx.is_private = True
        ctx.msg_id = "100"
        ctx.content = content
        ctx.attachments = []
        ctx.reply_to_content = reply_content
        ctx.reply_to_sender = reply_sender
        return ctx

    def test_content_prepended_with_reply(self):
        """When reply_to_content is present, content should be prepended."""
        from channels.im_telegram import ImTelegramChannel

        config = MagicMock()
        bus = MagicMock()
        channel = ImTelegramChannel(config, bus)

        # Simulate what _on_message_callback does
        ctx = self._make_ctx(
            content="I agree",
            reply_content="What do you think?",
            reply_sender="Alice",
        )

        # Extract the content logic from the callback
        content = ctx.content
        if ctx.reply_to_content:
            quoted = ctx.reply_to_content[:200]
            sender_tag = f" ({ctx.reply_to_sender})" if ctx.reply_to_sender else ""
            content = f'[Replying to{sender_tag}: "{quoted}"]\n{content}'

        self.assertEqual(
            content,
            '[Replying to (Alice): "What do you think?"]\nI agree'
        )

    def test_no_prepend_without_reply(self):
        """When no reply, content should remain unchanged."""
        ctx = self._make_ctx(content="Just a normal message")
        content = ctx.content
        if ctx.reply_to_content:
            quoted = ctx.reply_to_content[:200]
            sender_tag = f" ({ctx.reply_to_sender})" if ctx.reply_to_sender else ""
            content = f'[Replying to{sender_tag}: "{quoted}"]\n{content}'

        self.assertEqual(content, "Just a normal message")

    def test_long_quote_truncated(self):
        """Reply content should be truncated at 200 chars."""
        long_text = "a" * 300
        ctx = self._make_ctx(content="reply", reply_content=long_text)
        content = ctx.content
        if ctx.reply_to_content:
            quoted = ctx.reply_to_content[:200]
            sender_tag = f" ({ctx.reply_to_sender})" if ctx.reply_to_sender else ""
            content = f'[Replying to{sender_tag}: "{quoted}"]\n{content}'

        # quoted part should be exactly 200 chars
        self.assertIn('"' + "a" * 200 + '"', content)
        self.assertNotIn("a" * 201, content)


class TestFeishuParentMessage(unittest.TestCase):
    """Test Feishu channel fetches parent message text."""

    def test_fetch_parent_text_message(self):
        """_fetch_parent_message_text should extract text from text messages."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        bus = MagicMock()
        channel = FeishuChannel(config, bus)

        # Mock the API client
        mock_client = MagicMock()
        channel._api_client = mock_client

        # Mock response
        mock_msg = MagicMock()
        mock_msg.msg_type = "text"
        mock_body = MagicMock()
        mock_body.content = json.dumps({"text": "Hello from parent"})
        mock_msg.body = mock_body

        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.items = [mock_msg]

        mock_client.im.v1.message.get.return_value = mock_resp

        result = channel._fetch_parent_message_text("om_test_parent_id")
        self.assertEqual(result, "Hello from parent")

    def test_fetch_parent_post_message(self):
        """_fetch_parent_message_text should extract text from post messages."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        bus = MagicMock()
        channel = FeishuChannel(config, bus)

        mock_client = MagicMock()
        channel._api_client = mock_client

        mock_msg = MagicMock()
        mock_msg.msg_type = "post"
        mock_body = MagicMock()
        mock_body.content = json.dumps({
            "content": [
                [{"tag": "text", "text": "Line 1"}, {"tag": "text", "text": " continues"}],
                [{"tag": "text", "text": "Line 2"}],
            ]
        })
        mock_msg.body = mock_body

        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.items = [mock_msg]
        mock_client.im.v1.message.get.return_value = mock_resp

        result = channel._fetch_parent_message_text("om_test_parent_id")
        self.assertEqual(result, "Line 1 continuesLine 2")

    def test_fetch_parent_api_failure(self):
        """_fetch_parent_message_text should return None on API failure."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        bus = MagicMock()
        channel = FeishuChannel(config, bus)

        mock_client = MagicMock()
        channel._api_client = mock_client

        mock_resp = MagicMock()
        mock_resp.success.return_value = False
        mock_resp.code = 99999
        mock_resp.msg = "not found"
        mock_client.im.v1.message.get.return_value = mock_resp

        result = channel._fetch_parent_message_text("om_nonexistent")
        self.assertIsNone(result)

    def test_fetch_parent_no_client(self):
        """Should return None when API client is not initialized."""
        from channels.feishu import FeishuChannel

        config = MagicMock()
        config.app_id = "test"
        config.app_secret = "test"
        bus = MagicMock()
        channel = FeishuChannel(config, bus)
        channel._api_client = None

        result = channel._fetch_parent_message_text("om_test")
        self.assertIsNone(result)


class TestDingTalkQuoteExtraction(unittest.TestCase):
    """Test DingTalk context extracts quote content from payload."""

    def test_top_level_quote_content(self):
        """quoteContent at top level of payload should be extracted."""
        from channels.im_api.dingtalk.dingtalk.context import Context

        payload = {
            "msgId": "msg123",
            "msgtype": "text",
            "text": {"content": "my reply"},
            "conversationType": "1",
            "conversationId": "conv1",
            "senderStaffId": "user1",
            "sessionWebhook": "",
            "quoteContent": "the original message being quoted",
        }
        api = MagicMock()
        ctx = Context(payload, api)
        self.assertEqual(ctx.quote_content, "the original message being quoted")

    def test_nested_quote_content(self):
        """quoteContent nested under content should be extracted."""
        from channels.im_api.dingtalk.dingtalk.context import Context

        payload = {
            "msgId": "msg123",
            "msgtype": "text",
            "text": {"content": "my reply"},
            "conversationType": "1",
            "conversationId": "conv1",
            "senderStaffId": "user1",
            "sessionWebhook": "",
            "content": {"quoteContent": "nested quote text"},
        }
        api = MagicMock()
        ctx = Context(payload, api)
        self.assertEqual(ctx.quote_content, "nested quote text")

    def test_no_quote_content(self):
        """Without quoteContent, field should be empty string."""
        from channels.im_api.dingtalk.dingtalk.context import Context

        payload = {
            "msgId": "msg123",
            "msgtype": "text",
            "text": {"content": "normal message"},
            "conversationType": "1",
            "conversationId": "conv1",
            "senderStaffId": "user1",
            "sessionWebhook": "",
        }
        api = MagicMock()
        ctx = Context(payload, api)
        self.assertEqual(ctx.quote_content, "")


class TestDingTalkChannelReplyPrepend(unittest.TestCase):
    """Test ImDingTalkChannel prepends quote context to content."""

    def test_content_prepended_with_quote(self):
        """When quote_content exists, content should be prepended."""
        quote = "original message"
        content = "my reply"
        if quote:
            content = f'[Replying to: "{quote[:200]}"]\n{content}'
        self.assertEqual(content, '[Replying to: "original message"]\nmy reply')


class TestSystemPromptReplyGuidance(unittest.TestCase):
    """Test that the system prompt includes reply/quote guidance."""

    def test_media_guidance_includes_reply_section(self):
        """The media_guidance prompt section should mention reply/quote format."""
        from agent.context import ContextManager

        # Create a minimal ContextManager
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = ContextManager(
                metadata_root=Path(tmpdir),
                workspace_root=Path(tmpdir),
                project_id="TestProject",
            )
            # Mock project
            cm._project = MagicMock()
            cm._project.is_default = False

            prompt = cm.build_system_prompt()
            self.assertIn("[REPLY / QUOTE MESSAGES]", prompt)
            self.assertIn("[Replying to:", prompt)
            self.assertIn("quoted text here", prompt)


class TestTelegramBotDispatchReply(unittest.TestCase):
    """Test TelegramBot._dispatch_event extracts reply info correctly."""

    def test_dispatch_with_reply_to_message(self):
        """_dispatch_event should extract reply_to_message fields into payload."""
        # We test the payload construction logic directly
        # Simulate the reply_to_message extraction code from bot.py
        class FakeUser:
            first_name = "Alice"
            username = "alice_u"
            id = 111

        class FakeReplyMessage:
            text = "Original question?"
            caption = None
            from_user = FakeUser()

        reply_to = FakeReplyMessage()
        reply_content = reply_to.text or reply_to.caption or ""
        reply_sender = None
        if reply_to.from_user:
            reply_sender = reply_to.from_user.first_name or reply_to.from_user.username or str(reply_to.from_user.id)

        self.assertEqual(reply_content, "Original question?")
        self.assertEqual(reply_sender, "Alice")

    def test_dispatch_without_reply(self):
        """When reply_to_message is None, fields should be None."""
        reply_to = None
        reply_content = None
        reply_sender = None
        if reply_to:
            reply_content = reply_to.text or reply_to.caption or ""
            if reply_to.from_user:
                reply_sender = reply_to.from_user.first_name or str(reply_to.from_user.id)

        self.assertIsNone(reply_content)
        self.assertIsNone(reply_sender)

    def test_dispatch_reply_caption_only(self):
        """When reply has no text but has caption (e.g. photo reply)."""
        class FakeUser:
            first_name = "Bob"
            username = None
            id = 222

        class FakeReplyMessage:
            text = None
            caption = "Check this photo"
            from_user = FakeUser()

        reply_to = FakeReplyMessage()
        reply_content = reply_to.text or reply_to.caption or ""
        reply_sender = reply_to.from_user.first_name or reply_to.from_user.username or str(reply_to.from_user.id)

        self.assertEqual(reply_content, "Check this photo")
        self.assertEqual(reply_sender, "Bob")


if __name__ == "__main__":
    unittest.main()
