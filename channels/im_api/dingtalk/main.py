import logging
import os

from dingtalk import DingTalkBot

logging.basicConfig(level=logging.INFO)

bot = DingTalkBot(
    client_id=os.getenv("DINGTALK_CLIENT_ID", ""),
    client_secret=os.getenv("DINGTALK_CLIENT_SECRET", ""),
    robot_code=os.getenv("DINGTALK_ROBOT_CODE", ""),
)


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
