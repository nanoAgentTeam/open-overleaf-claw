# History 设计

## 什么是 History

History 是对话历史的持久化层。每个 session 有独立的历史记录，存储在 `.bot/history.jsonl` 中。

History 解决的核心问题是：Agent 重启或 session 恢复时，能够加载之前的对话上下文继续工作。

## 存储格式

使用 JSONL（每行一个 JSON 对象），记录每条消息：

- 角色（user / assistant / tool）
- 内容
- 时间戳
- 工具调用信息（如果有）

JSONL 的好处是追加写入，不需要读取整个文件就能添加新记录。

## 加载策略

加载历史时不是全部加载，而是取最近 N 条消息。这个数量由 `config/features.json` 中的参数控制。

加载后的历史会被注入到发送给 LLM 的消息列表中，位于 system prompt 之后、当前用户消息之前。

## Auto-Summary

当历史消息累积到一定数量（默认每 10 条消息触发一次，从第 20 条开始），系统会在后台生成摘要：

1. 取出较早的历史消息
2. 用 LLM 生成摘要
3. 摘要存入 `active_context.md`
4. 下次组装 prompt 时，摘要作为上下文注入

这样既保留了关键信息，又控制了 token 消耗。

## Trajectory 记录

除了对话历史，系统还记录 trajectory（轨迹）——每一步的工具调用、参数、返回值、耗时。这主要用于调试和分析，不会注入到 LLM 上下文中。

## 关键设计决策

**为什么用 JSONL 而不是数据库？** 简单、可读、易于调试。每个 session 的历史就是一个文件，可以直接用文本编辑器查看。

**为什么不加载全部历史？** Token 限制。一个长 session 可能有几百条消息，全部加载会超出 LLM 上下文窗口。

**为什么 auto-summary 在后台运行？** 不阻塞用户交互。摘要生成需要调用 LLM，可能需要几秒，放在后台不影响响应速度。

## 相关文件

- `agent/memory/logger.py` — HistoryLogger 实现
- `agent/memory/trace.py` — Trace 日志
- `config/features.json` — 历史加载和摘要的参数配置
