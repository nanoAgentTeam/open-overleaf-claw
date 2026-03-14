# Context Management 设计

## 什么是 Context Management

Context Management 负责组装发送给 LLM 的完整消息列表。它决定了 Agent "看到"什么——system prompt 的内容、历史消息的多少、记忆的注入。

这是影响 Agent 行为最关键的模块之一。

## System Prompt 组装

System prompt 由多个片段拼接而成，顺序大致是：

1. **Identity**：Agent 的身份和角色描述
2. **Mode 指引**：当前模式（Default/Project）下的行为指引
3. **Workspace 信息**：当前项目名、session 名、可用路径
4. **权限声明**：当前角色能做什么、不能做什么
5. **Memory 注入**：长期记忆和活跃上下文
6. **Memory Protocol**：告诉 Agent 如何使用记忆工具

这些片段来自 `config/prompts/` 下的模板文件，通过变量替换（如 `{{project_name}}`、`{{session_id}}`）动态生成。

## 消息列表结构与 Step Boundary

一次 ReAct 循环中，消息列表分为两个区域：

```
[system prompt] [history...] [user message] | [assistant+tool pairs...]
^--- context 区域 (不压缩) ---^  ^--- steps 区域 (压缩目标) ---^
                                  ↑
                            step_boundary
```

`step_boundary` 是 `build_messages()` 返回后的 `len(messages)`，标记了 context 和 steps 的分界。所有压缩操作（L1/L2/Meta-Reset）都只作用于 steps 区域，context 区域始终完整保留。

## 上下文压缩

LLM 有 token 上限，长对话会超限。系统采用统一的压缩架构，AgentLoop 和 AgentEngine 共享同一套压缩原语。

### 共享原语（`core/llm/middleware.py`）

| 函数/常量 | 用途 |
|-----------|------|
| `StepCompressionMiddleware._split_steps()` | 将 steps 分割为 head(前2步) / middle / tail(后2步) |
| `StepCompressionMiddleware._rule_based_summary()` | 对 middle 生成规则摘要 |
| `_estimate_tokens()` | 估算消息列表的 token 数 |
| `infer_context_limit()` | 根据模型名推断上下文窗口大小 |
| `MAX_TOOL_OUTPUT_LENGTH` (32k) | 工具输出截断阈值 |
| `TOOL_TRUNCATION_EXEMPT` | 写入类工具豁免集合 |

### Tier 0：工具输出截断

单次工具返回如果超过 `MAX_TOOL_OUTPUT_LENGTH`（32k 字符），会被截断。写入类工具（`write_file`、`str_replace`、`patch_file`、`insert_content`）豁免截断。

AgentLoop 和 AgentEngine 共用同一套常量和豁免集合。

### Tier 1：主动压缩（L1，70% 阈值）

当消息总 token 数达到上限的 70% 时，对 steps 区域执行压缩：

1. 用 `_split_steps()` 将 steps 分为 head（前 2 个 assistant+tool 步骤）、middle、tail（后 2 个步骤）
2. 用 `_rule_based_summary()` 对 middle 生成摘要
3. 重组为：`context + head + [summary] + tail`

Context 区域（system + history + user）完整保留，不受影响。

AgentEngine 的 L1 额外支持 LLM 摘要（通过 `session.metadata["llm_client"]`），AgentLoop 只用规则摘要。

### Tier 2：紧急恢复（L2，context_length_exceeded）

如果 LLM 返回 `context_length_exceeded` 错误：

1. 用 `_split_steps()` 分割 steps 区域
2. 丢弃 middle，只保留 head + tail
3. 重组为：`context + head + tail`
4. 重试 LLM 调用

### Meta-Reset（死锁恢复）

当循环检测触发 Meta-Diagnosis 后，重置消息列表：

- 保留完整 context 区域（`messages[:step_boundary]`）
- 丢弃所有 steps
- 追加诊断结果作为新的 user message

三种压缩操作的语义一致：都用 `step_boundary` 分割，都只压缩 steps 区域。

## Token 估算

系统对 token 数量做保守估算（`_estimate_tokens()`）：
- ASCII 字符：约 3 字符 = 1 token
- 非 ASCII 字符（中文等）：约 1 字符 = 2 token（更保守，因为中文 token 化效率低）

## Context Limit 推断

`infer_context_limit()` 根据模型名推断上下文窗口：
- GPT-4 系列：128k
- Claude-3 系列：200k
- Gemini 系列：1M
- 默认：256k

## 统一后的对照表

| 维度 | AgentLoop | AgentEngine |
|------|-----------|-------------|
| L1 (70%) | `_split_steps` + `_rule_based_summary` | `_split_steps` + `_rule_based_summary`（或 LLM 摘要） |
| L2 (撞墙) | `_split_steps`（丢弃 middle） | `_split_steps`（丢弃 middle） |
| Tool 截断 | `MAX_TOOL_OUTPUT_LENGTH` + `TOOL_TRUNCATION_EXEMPT` | 同左 |
| Token 估算 | `_estimate_tokens` | `_estimate_tokens` |
| Context limit | `infer_context_limit` | `infer_context_limit` |

## 关键设计决策

**为什么用模板而不是硬编码 prompt？** 灵活性。不同角色、不同模式需要不同的 prompt，模板化让修改不需要改代码。

**为什么 70% 就开始压缩？** 留余量。如果等到 100% 才压缩，可能来不及——一次大的工具返回就会超限。

**为什么 L1 只压缩 steps 不压缩 history？** Steps 是当前轮次的工具调用链，是最大的 token 消耗源。History 由 `HistorySummaryMiddleware` 单独管理（按轮次裁剪）。

**为什么对中文用更保守的估算？** 中文的 tokenizer 效率不如英文，宁可多压缩也不要超限失败。

## 相关文件

- `agent/context.py` — ContextManager 实现
- `agent/loop.py` — AgentLoop 中的 L1/L2 压缩调用
- `core/llm/middleware.py` — 共享压缩原语和常量
- `core/llm/engine.py` — AgentEngine 中的 L1/L2 压缩
- `config/prompts/` — prompt 模板目录
- `config/vfs.json` — 路径和记忆路径配置
