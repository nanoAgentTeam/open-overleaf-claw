# Command System 设计

## 什么是 Command System

Command System 处理以 `/` 开头的斜杠命令。这些命令提供快捷操作，不需要经过 LLM 思考。

## 命令定义

所有命令在 `config/commands.json` 中声明式定义，每个命令包含：

- **name**：命令名称（如 `reset`、`compile`）
- **description**：描述
- **handler**：处理器类名
- **type**：`terminal`（直接执行）或 `fallthrough`（改写后交给 LLM）
- **project_only**：是否只在项目中可用

## 两种命令类型

### Terminal 命令

直接执行，不进入 LLM。执行完毕后直接返回结果。

例如：
- `/reset` — 清空当前 session 的对话历史
- `/compile` — 编译当前项目的 LaTeX
- `/sync pull` / `/sync push` — Overleaf 同步
- `/back` — 返回 Default
- `/git` — 进入 Git 管理子会话

### Fall-through 命令

命令被改写为一条消息，然后交给 LLM 处理。

例如：
- `/task 调研 MoE` → 改写为触发 Deep Research 的消息，LLM 调用 task_planner 工具

## 路由流程

```
用户输入 "/compile"
  ↓
CommandRouter 匹配命令
  ↓
检查 project_only（是否需要在项目中）
  ↓
Terminal → 直接执行 handler，返回结果
Fall-through → 改写消息，继续进入 AgentLoop
```

## 关键设计决策

**为什么用 JSON 定义命令？** 可扩展。新增命令只需要写一个 handler 类并在 JSON 中注册，不需要修改路由逻辑。

**为什么区分 terminal 和 fall-through？** 有些操作（如编译、同步）是确定性的，不需要 LLM 参与。有些操作（如调研）需要 LLM 来规划和执行。

## 相关文件

- `config/commands.json` — 命令定义
- `agent/services/command_router.py` — 命令路由器
- `agent/services/commands.py` — 命令处理器实现
