import logging
from dotenv import load_dotenv
from qq import QQBot
from qq.config import get_qq_config
# 加载环境变量 (.env)
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app_id, app_secret = get_qq_config()
# 初始化机器人
bot = QQBot(app_id=app_id, app_secret=app_secret)  # 会自动从环境变量加载 APP_ID 和 CLIENT_SECRET

@bot.on_message()
async def main_handler(ctx):
    """
    统一消息处理器：优先匹配特殊指令，避免重复回复触发去重报错
    """
    # 统一记录收到的消息日志
    logging.info(f"收到消息: {ctx.content} (来自 {'私聊' if ctx.is_private else '群聊'})")

    content = ctx.content.strip()

    # 1. 优先匹配特殊指令 (忽略大小写)
    if content.lower() == "ping":
        await ctx.reply("pong!")
        return

    if "表情包" in content:
        # 回复指定的本地图片
        meme_path = "./qq/memes/meme1.png"
        try:
            await ctx.reply_image(meme_path)
        except Exception as e:
            logging.error(f"发送表情包失败: {e}")
            await ctx.reply("哎呀，表情包丢了...")
        return

    if "网图" in content:
        # 回复网络图片 URL
        web_meme_url = "https://media1.tenor.com/m/q1yvPMlMoHAAAAAd/chinese.gif"
        try:
            await ctx.reply_image(web_meme_url)
        except Exception as e:
            logging.error(f"发送网络表情包失败: {e}")
            await ctx.reply("哎呀，网络图片加载失败了...")
        return

    # 2. 可以在这里继续添加其他指令匹配
    # elif content == "帮助":
    #     await ctx.reply("这是帮助信息...")
    #     return

    # 3. 默认处理逻辑 (如复读)
    logging.info(f"收到普通消息: {content} (来自 {'私聊' if ctx.is_private else '群聊'})")
    await ctx.reply(f"已收到消息: {content}")

if __name__ == "__main__":
    bot.run()
