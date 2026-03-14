# AgentLoop 设计

## 什么是 AgentLoop

AgentLoop 是系统的心脏。它实现了 ReAct（Reasoning + Acting）循环：接收用户消息 → 调用 LLM 思考 → 执行工具 → 把结果反馈给 LLM → 继续思考 → 直到不再需要工具调用。

每一轮对话就是一次 AgentLoop 的运行。

## 运行流程

```
用户消息进入
    ↓
加载历史消息（从 HistoryLogger）
    ↓
组装完整消息列表（system prompt + history + 当前消息）
    ↓
记录 step_boundary = len(messages)
    ↓
进入迭代循环（最多 100 轮）：
    ├── L1 压缩检查（70% 阈值，只压缩 steps 区域）
    ├── 调用 LLM（带工具定义）
    ├── 如果 context_length_exceeded → L2 紧急恢复 → 重试
    ├── 如果 LLM 返回工具调用 → 并行执行工具 → 结果加入消息
    ├── 如果 LLM 返回纯文本 → 循环结束
    └── 检查循环检测 / Meta-Diagnosis
    ↓
Flush 待提交的文件（auto commit）
    ↓
返回响应
```

## Step Boundary

`step_boundary` 是 `build_messages()` 返回后的消息数量，标记 context 和 steps 的分界。所有压缩操作都基于这个分界点：

- L1：`messages[:step_boundary]` + 压缩后的 steps
- L2：`messages[:step_boundary]` + head + tail（丢弃 middle）
- Meta-Reset：`messages[:step_boundary]` + 诊断消息

## 工具调用

LLM 返回的工具调用会被并行执行（asyncio.gather）。每个工具调用的结果会被加入消息历史，供 LLM 在下一轮参考。

工具的可用列表由 ToolRegistry 根据当前模式和角色动态过滤。

工具输出超过 32k 字符时会被截断，写入类工具（`write_file`、`str_replace` 等）豁免。

## 循环检测与 Meta-Diagnosis

系统追踪最近 20 次工具调用的 fingerprint（`{name, args}`）：

1. 同一 fingerprint 出现 7 次 → 注入 `[LOOP DETECTION]` 警告，`consecutive_deadlocks += 1`
2. `consecutive_deadlocks >= 3` → 触发 **Meta-Diagnosis**：用独立 LLM 调用分析死锁原因，执行 Meta-Reset
3. Meta-Reset：保留完整 context（`messages[:step_boundary]`），丢弃所有 steps，注入诊断结果

`has_loop_warning` 标志确保只有当本轮所有工具结果都没有循环警告时，才重置 `consecutive_deadlocks`。

## 上下文压缩

AgentLoop 使用 `core/llm/middleware.py` 中的共享压缩原语：

- **L1（70% 阈值）**：`_split_steps()` + `_rule_based_summary()`，保留 context + head + summary + tail
- **L2（context_length_exceeded）**：`_split_steps()`，保留 context + head + tail，丢弃 middle
- **Token 估算**：`_estimate_tokens()`
- **Context limit**：`infer_context_limit()`

详见 [04_Context_Management.md](04_Context_Management.md)。

## 命令路由

用户消息如果以 `/` 开头，会先经过 CommandRouter：

- **Terminal 命令**（如 `/reset`、`/compile`）：直接执行，不进入 LLM
- **Fall-through 命令**（如 `/task`）：改写消息后继续进入 LLM 处理

## 关键设计决策

**为什么最多 100 轮？** 防止失控。普通 chat 通常 1-5 步就结束。Task Mode 的 FINALIZE 阶段可能需要大量步骤整合产出，100 步提供了足够的余量。剩 20 步时系统会提醒 Agent 收尾。

**为什么工具并行执行？** LLM 经常一次返回多个工具调用（比如同时读多个文件），并行执行显著提升速度。

**为什么需要 Meta-Diagnosis 而不是直接终止？** 直接终止太粗暴。Meta-Diagnosis 尝试理解问题并给出解决方案，让 Agent 有机会自我修复。

## 相关文件

- `agent/loop.py` — AgentLoop 主循环
- `agent/context.py` — ContextManager（prompt 组装、消息构建）
- `core/llm/middleware.py` — 共享压缩原语
- `agent/services/command_router.py` — 命令路由
- `agent/services/commands.py` — 命令处理器
