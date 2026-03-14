import unittest

from channels.im_api.telegram.telegram.api import markdown_to_telegram_html
from channels.im_api.telegram.telegram.context import Context


class _FakeAPI:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, content, reply_to_message_id=None):
        self.calls.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to_message_id": reply_to_message_id,
            }
        )
        return {"ok": True}


class TestTelegramIMAPI(unittest.IsolatedAsyncioTestCase):
    def test_markdown_to_html(self):
        raw = "**bold**\n- item\n`a<b>`\n[link](https://example.com)"
        html = markdown_to_telegram_html(raw)

        self.assertIn("<b>bold</b>", html)
        self.assertIn("• item", html)
        self.assertIn("<code>a&lt;b&gt;</code>", html)
        self.assertIn('<a href="https://example.com">link</a>', html)

    async def test_context_fields_and_reply(self):
        api = _FakeAPI()
        payload = {
            "content": "hello",
            "message_id": 123,
            "chat_id": -100001,
            "user_id": 42,
            "username": "alice",
            "first_name": "Alice",
            "is_private": False,
            "media_paths": ["/tmp/a.jpg"],
        }

        ctx = Context(payload, api)

        self.assertEqual(ctx.content, "hello")
        self.assertEqual(ctx.msg_id, "123")
        self.assertEqual(ctx.chat_id, "-100001")
        self.assertEqual(ctx.user_id, "42")
        self.assertFalse(ctx.is_private)
        self.assertEqual(ctx.attachments, ["/tmp/a.jpg"])

        await ctx.reply("pong")
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0]["chat_id"], "-100001")
        self.assertEqual(api.calls[0]["content"], "pong")
        self.assertEqual(api.calls[0]["reply_to_message_id"], "123")


if __name__ == "__main__":
    unittest.main()
