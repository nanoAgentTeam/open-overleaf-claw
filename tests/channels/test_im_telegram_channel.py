import unittest

from bus.queue import MessageBus
from channels.im_telegram import ImTelegramChannel
from config.schema import Config


class _FakeBot:
    def __init__(self):
        self.stop_called = False

    async def stop(self):
        self.stop_called = True


class TestImTelegramChannel(unittest.IsolatedAsyncioTestCase):
    async def test_stop_calls_underlying_bot_stop(self):
        cfg = Config()
        bus = MessageBus()
        channel = ImTelegramChannel(cfg, bus)
        fake_bot = _FakeBot()
        channel._bot = fake_bot
        channel._running = True

        await channel.stop()

        self.assertTrue(fake_bot.stop_called)
        self.assertFalse(channel.is_running)


if __name__ == "__main__":
    unittest.main()
