# 🤖 QQ Bot (qq 包) 开发者手册

基于 **插件化模式** 和 **装饰器驱动** 设计的轻量级 QQ 机器人 Python 开发框架。

## 🚀 快速开始

### 1. 安装依赖
确保已安装 Python 3.8+，并安装以下依赖：
```bash
pip install aiohttp pydantic python-dotenv
```

### 2. 配置环境变量
在项目根目录创建 `.env` 文件：
```env
APP_ID=你的AppID
CLIENT_SECRET=你的AppSecret
```

### 3. 基础代码 (`main.py`)
```python
import logging
from dotenv import load_dotenv
from qq import QQBot

load_dotenv()
logging.basicConfig(level=logging.INFO)

bot = QQBot()

@bot.on_message()
async def handle_msg(ctx):
    if ctx.content == "你好":
        await ctx.reply("你好！我是 QQ 机器人助手。")

if __name__ == "__main__":
    bot.run()
```

---

## 🛠 核心接口说明

### `Context` (上下文对象)
每个插件函数都会接收到一个 `ctx` 对象，它是你与用户交流的基础接口：

| 属性/方法 | 类型 | 说明 |
| :--- | :--- | :--- |
| `ctx.content` | `str` | 用户发送的消息文本内容（已去首尾空格）。 |
| `ctx.user_id` | `str` | 发送者的 OpenID。 |
| `ctx.group_id` | `str` | 群聊 OpenID（私聊消息时为 `None`）。 |
| `ctx.is_private` | `bool` | 是否为私聊消息。 |
| `ctx.attachments` | `list` | 消息附件列表（如图片 URL 等）。 |
| `await ctx.reply(text)` | `async` | 发送文本回复，自动处理私聊/群聊及消息去重。 |
| `await ctx.reply_image(path)` | `async` | **发送图片**，支持本地文件路径或网络 URL。 |

---

## 🖼 图片处理功能

框架内置了强大的图片处理逻辑，支持 **本地表情包** 和 **网络图片**。

### 1. 回复本地图片
只需传入本地文件路径，框架会自动完成读取、Base64 编码和上传。
```python
@bot.on_message()
async def send_meme(ctx):
    if "表情包" in ctx.content:
        await ctx.reply_image("./qq/memes/meme1.png")
```

### 2. 回复网络图片
框架采用了 **本地中转模式**（下载 -> 重新上传），有效解决了腾讯服务器直接抓取外链时经常出现的 `850027 上传超时` 错误。
```python
@bot.on_message()
async def send_web_img(ctx):
    if "网图" in ctx.content:
        await ctx.reply_image("https://example.com/image.jpg")
```

---

## 📂 项目结构
```text
.
├── qq/                  # 核心 API 包
│   ├── __init__.py      # 导出接口
│   ├── bot.py           # 插件管理与分发核心
│   ├── context.py       # 消息上下文接口
│   ├── api.py           # API 请求与富媒体上传封装
│   ├── gateway.py       # WebSocket 连接管理
│   └── models.py        # 数据模型
├── main.py              # 业务逻辑入口
├── .env                 # 配置文件 (敏感信息)
└── README.md            # 本说明文档
```

## ⚠️ 常见问题

1.  **消息被去重 (40054005)**：请确保对同一条消息只调用一次 `ctx.reply()` 或 `ctx.reply_image()`。建议在 `if-return` 逻辑中处理。
2.  **导入错误**：IDE (如 VS Code) 提示无法解析导入时，请确认已选择正确的 Python 解释器并安装了依赖，这不影响程序运行。
