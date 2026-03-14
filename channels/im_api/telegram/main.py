import logging
import os

from telegram import TelegramBot

logging.basicConfig(level=logging.INFO)

bot = TelegramBot(token=os.getenv("TELEGRAM_BOT_TOKEN", ""))


@bot.on_message()
async def handler(ctx):
    text = ctx.content.strip()
    if not text:
        return

    if text.lower() == "ping":
        await ctx.reply("pong")
        return

    await ctx.reply(f"received: {text}")


if __name__ == "__main__":
    bot.run()
