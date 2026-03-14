# Chat & Channel 设计

## 什么是 Chat & Channel

Channel 是用户与 Bot 交互的入口。系统支持三种 Channel：CLI（本地终端）、飞书、Telegram。它们共享同一个 Agent 核心，通过 MessageBus 解耦。

## 消息流向

```
用户输入
  ↓
Channel（CLI / 飞书 / Telegram）
  ↓
MessageBus.inbound（异步队列）
  ↓
AgentLoop 处理
  ↓
MessageBus.outbound（异步队列）
  ↓
Channel 渲染输出
```

所有 Channel 都不直接调用 AgentLoop，而是通过 MessageBus 传递消息。这意味着：

- Agent 不知道消息来自哪个 Channel
- 多个 Channel 可以同时连接
- 新增 Channel 不需要修改 Agent 代码

## CLI Channel

交互式终端，提示符显示当前项目和 session：

```
[Default:cli:default] You: ...
[MoE_Research:0217_01] You: ...
```

支持所有功能，包括 hot reload（`/switch`、`/new` 不需要重启）。

CLI 还有一个单消息模式（`-m` 参数），用于脚本调用和 cron 定时任务。

## 飞书 Channel

使用 WebSocket 连接，不需要公网 IP。特点：

- 支持流式输出：通过消息卡片（Interactive Message Card）实现，每 300ms 更新一次
- 支持多流渲染：主 Agent 和子 Agent 的进度可以同时展示
- 支持文本、图片、语音、文档等多种消息类型

## Telegram Channel

使用长轮询（Long Polling）。特点：

- 支持 Markdown 格式输出
- 支持文本、图片、语音、音频、文档
- 通过 `allowFrom` 配置白名单，限制谁可以使用

## 关键设计决策

**为什么用 MessageBus 解耦？** 关注点分离。Channel 只负责收发消息和渲染，不需要理解 Agent 的内部逻辑。Agent 只负责处理消息，不需要知道消息来自哪里。

**为什么飞书用 WebSocket 而不是 Webhook？** 不需要公网 IP。研究者的开发环境通常在内网，WebSocket 可以主动连接飞书服务器。

**为什么 CLI 支持单消息模式？** 方便自动化。配合 cron 可以实现定时调研，配合脚本可以批量处理。

## 相关文件

- `cli/main.py` — CLI 入口和交互循环
- `cli/renderer.py` — 终端渲染器
- `channels/base.py` — Channel 抽象接口
- `channels/telegram.py` — Telegram 实现
- `channels/feishu.py` — 飞书实现
- `bus/queue.py` — MessageBus
- `bus/events.py` — 消息事件定义
