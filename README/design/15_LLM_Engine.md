# LLM Engine 设计

## 什么是 LLM Engine

LLM Engine 是系统与大语言模型交互的底层引擎。它封装了 API 调用、流式输出、工具调用协议，并提供 Middleware 管道来拦截和增强行为。

## Provider 抽象

系统通过 Provider 抽象支持不同的 LLM 服务：

- **OpenAI Provider**：支持 OpenAI 及所有兼容 API（如 DeepSeek）
- **LiteLLM Provider**：通过 LiteLLM 库支持更多模型

Provider 在 `settings.json` 中配置，包括 API key、base URL、模型名称等。切换模型只需要改配置，不需要改代码。

## Middleware 管道

LLM Engine 在每次 LLM 调用前后插入 Middleware，形成责任链：

### ExecutionBudgetManager（执行预算）

限制单次对话的总迭代次数（默认 50）。超过预算时通过 `system_config.set()` 注入 CRITICAL 警告，要求 AI 立即给出最终答案。这是软限制（通过提示词），与 `run()` 的 `max_iterations` 硬限制配合使用。

### HistorySummaryMiddleware（历史裁剪）

操作 history 区域（`history_boundary` 之前的消息）。当用户轮次超过 `max_rounds`（默认 30）时，丢弃最旧的轮次，只保留最近 `keep_rounds`（默认 10）轮。

不生成摘要——摘要由应用层（如 `active_context.md`）负责。

### StepCompressionMiddleware（步骤压缩）

操作 steps 区域（`history_boundary` 之后的消息）。提供 L1 压缩和共享的静态工具方法：

- `_split_steps(steps)`：将 steps 分为 head（前 2 步）/ middle / tail（后 2 步）
- `_rule_based_summary(middle)`：对 middle 生成规则摘要（编号列表，每步一行）
- `_llm_summary(middle, client, model)`：用 LLM 生成更精炼的摘要（async）

L1 触发条件：token 估算超过 `model_context_limit * 0.7`。

这些静态方法同时被 AgentLoop 直接调用，实现了压缩逻辑的统一。

## 内联循环检测

AgentEngine 在工具执行阶段内联了循环检测（不通过 Middleware）：

1. 维护 `action_history`（最近 20 次工具调用的 fingerprint）
2. 同一 fingerprint 出现 7 次 → 触发 `[LOOP DETECTION]` 警告
3. 连续 3 次死锁（`consecutive_deadlocks >= 3`）→ 触发 Meta-Diagnosis
4. 用 `has_loop_warning` 标志扫描所有工具结果后，才决定是否重置 `consecutive_deadlocks`

## 工具输出截断

使用共享常量（`core/llm/middleware.py`）：
- `MAX_TOOL_OUTPUT_LENGTH`（32k）：超过此长度的工具输出被截断
- `TOOL_TRUNCATION_EXEMPT`：写入类工具（`write_file`、`str_replace` 等）豁免截断

## 流式输出

LLM Engine 支持流式输出（streaming），Agent 的回复可以逐 token 展示给用户，而不是等全部生成完毕。

在 CLI 中直接流式打印，在飞书中通过消息卡片 patch 实现流式更新。

## 关键设计决策

**为什么循环检测内联而不用 Middleware？** 循环检测需要在工具执行阶段拦截（决定是否执行工具），而 Middleware 在 LLM 调用前后执行，时机不对。

**为什么 Middleware 用责任链模式？** 可组合性。每个 Middleware 关注一个方面，可以独立启用/禁用，也方便新增。

**为什么压缩原语用静态方法？** 让 AgentLoop 可以直接调用，不需要实例化 Middleware。统一了两套系统的压缩逻辑。

## 相关文件

- `core/llm/engine.py` — AgentEngine 实现
- `core/llm/middleware.py` — Middleware 实现（含共享压缩原语和常量）
- `core/llm/types.py` — 数据模型（AgentSession, SystemPromptConfig 等）
- `core/llm/providers.py` — Provider 工厂
- `providers/openai_provider.py` — OpenAI Provider
- `providers/litellm_provider.py` — LiteLLM Provider
