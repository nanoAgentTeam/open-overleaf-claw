import unittest

from channels.im_api.dingtalk.dingtalk.message_utils import (
    detect_markdown_and_extract_title,
    extract_message_content,
)


class TestDingTalkMessageUtils(unittest.TestCase):
    def test_detect_markdown_and_title(self):
        use_markdown, title = detect_markdown_and_extract_title("# 标题\n内容", {}, "默认")
        self.assertTrue(use_markdown)
        self.assertEqual(title, "标题")

    def test_extract_text_message(self):
        content = extract_message_content(
            {
                "msgtype": "text",
                "text": {"content": "  你好  "},
            }
        )
        self.assertEqual(content["text"], "你好")
        self.assertEqual(content["message_type"], "text")

    def test_extract_rich_text_with_picture(self):
        content = extract_message_content(
            {
                "msgtype": "richText",
                "content": {
                    "richText": [
                        {"type": "text", "text": "请看"},
                        {"type": "picture", "downloadCode": "abc123"},
                    ]
                },
            }
        )
        self.assertEqual(content["text"], "请看")
        self.assertEqual(content["media_code"], "abc123")
        self.assertEqual(content["media_type"], "image")


if __name__ == "__main__":
    unittest.main()
