# Task Mode 设计（SDD 架构）

## 什么是 Task Mode

Task Mode 是系统的深度研究执行模式。用户通过 `/task` 发起复杂任务后，系统进入 Task Mode，经历 UNDERSTAND → PLAN → EXECUTE → FINALIZE 四个阶段，将任务拆解为 DAG 并通过 Worker→Reviewer 循环完成。

与普通 chat 模式的区别：主 Agent 不直接执行研究工作，而是作为项目经理，规划任务、调度 Worker、审核产出、整合交付。

## 四阶段生命周期

```
/task "调研 LLM 记忆系统"
    ↓
[UNDERSTAND] 主 Agent 理解需求，收集背景信息
    ↓
[PLAN] 生成 TaskGraph（DAG），用户确认
    ↓
[EXECUTE] BatchRunner 按拓扑序调度 Worker→Reviewer 循环
    ↓
[FINALIZE] 主 Agent 整合所有 Worker 产出为最终交付物
    ↓
task_commit → 提交到 git，可进入下一轮 /task
```

### UNDERSTAND

主 Agent 阅读项目文件、搜索资料，理解用户需求的范围和约束。这个阶段主 Agent 可以自由使用所有工具。

### PLAN

调用 Planner 生成 TaskGraph。每个节点是一个子任务，包含：
- 标题、描述、验收标准（spec）
- 依赖关系（哪些任务必须先完成）
- 分配的 Agent 角色名

无依赖的任务可以并行执行。

### EXECUTE

BatchRunner 按拓扑序找出就绪任务，交给 SDDExecutor 执行。每个任务经历：

1. **创建 Worker Session** — 隔离的 overlay 目录
2. **依赖注入** — 祖先任务的产出复制到 Worker 目录下的 `{dep_id}/` 子目录
3. **三层写保护** — 防止 Worker 写入依赖目录（详见下文）
4. **Worker 执行** — 独立 LLM 循环（最多 15 步）
5. **Reviewer 审核** — 独立 LLM 检查产出质量（最多 10 步）
6. **通过/重试** — 审核不通过则反馈给 Worker 重做（最多 3 次）
7. **Merge** — Worker overlay 产出（排除依赖目录）复制到 `core/_task_workers/{task_id}_r{round_id}/`

### FINALIZE

所有任务完成后，主 Agent 进入 FINALIZE：

- `_task_workers/` 被设为只读（chmod 444/555）
- 主 Agent 阅读所有 Worker 产出，重新组织为干净的最终交付物
- 交付物写入主工作区根目录（不保留 `tXX_rN/` 目录结构）
- 调用 `task_commit` 提交

## 依赖注入与写保护

Worker 需要读取上游任务的产出，但不能修改它们。系统通过三层防御实现：

### Layer 1：Session 级拦截

`Session.write_target()` 检查写入路径的顶层目录是否在 `_protected_prefixes` 中。命中则抛出 `PermissionError`。

这拦截了所有通过 `write_file`、`str_replace` 的写入。

### Layer 2：Prompt 提示

Worker 的 system prompt 中注入警告：

```
IMPORTANT — Dependency directories are READ-ONLY:
  Directories: t1, t2
  You CAN read files from them.
  You CANNOT write or modi inside them.
  All your outputs must be simple filenames in the current directory.
```

### Layer 3：OS 级权限

依赖目录的文件设为 444（只读），目录设为 555。这拦截了通过 `bash echo >` 等绕过 Session 的写入。

重试前和 merge 前会恢复权限（`_restore_dep_permissions`），避免 shutil 操作失败。

### bash cp 的特殊处理

macOS 的 `cp` 会继承源文件权限。Worker 如果 `cp t1/file.md ./file.md`，目标文件也是 444。`Session.write_target()` 检测到目标文件不可写时，自动 `chmod 644` 恢复。

## Worker 工具沙箱

Worker 使用受限的工具集（`_get_sandboxed_tools`）：

**提供的工具**（锚定到 Worker overlay）：
- `read_file`、`write_file`、`str_replace`、`ls`、`bash`
- `web_fetch`、`latex_compile`、`overleaf`
- 以及全局工具中非递归的部分（如 `arxiv_search`）

**禁用的工具**：
- 递归工具：`create_subagent`、`open_task_planner` 等
- 管理工具：`project_manager`、`session_manager`、`config_manager`、`manage_todo`

Worker 的文件工具绑定到 Worker Session，写入自动重定向到 overlay。

## Reviewer 设计

Reviewer 是独立的 LLM 调用，使用与 Worker 相同的沙箱工具集（可以 `ls` 和 `read_file` 查看产出）。

Reviewer prompt 包含：
- Worker 身份（`task.assigned_agent`）
- 任务目标（`task.description`）
- 验收标准（`task.spec`）
- 依赖目录说明（哪些目录是上游产出，不属于当前 Worker）

Reviewer 必须以 `CONCLUSION: PASS` 或 `CONCLUSION: FAIL: <reason>` 结尾。系统用正则解析结论，fallback 到关键词匹配。

## 多轮执行（Round）

`task_commit` 提交当前轮次后，用户可以再次 `/task` 发起新一轮。`round_id` 递增，Worker 产出写入 `_task_workers/{task_id}_r{new_round_id}/`。

`BatchRunner` 通过 `graph is not` 检查检测 TaskGraph 变化，自动重建。

## LaTeX 编译引擎自动检测

`LaTeXCompileTool` 和 `Project._compile` 在编译前扫描 tex 文件头 50 行：

| 检测到的宏包 | 选择的引擎 |
|---|---|
| `ctex`、`xeCJK`、`fontspec`、`unicode-math` | xelatex |
| `luacode`、`luatextra` | lualatex |
| 其他 | pdflatex（默认） |

用户在 `project.yaml` 中显式配置的引擎不会被覆盖（仅在默认 pdflatex 时触发检测）。

## 步数管理与提醒

主 Agent 每轮对话最多 100 步（`config.features.agent.max_iterations`）。

| 剩余步数 | 提醒级别 |
|---|---|
| > 20 | 正常显示 `Step X/100` |
| ≤ 20 | ⚠️ Warning：提醒收尾和 commit |
| ≤ 5 | 🚨 Last Call：要求立即 commit |

## Context 压缩补丁

除了原有的 Tier 2（迭代开头 70% 阈值检查）和 Tier 3（LLM 报错后紧急恢复），新增了 **Tier 2.5**：

在每次 tool result 追加到 messages 之后，立即检查 context 大小。如果超过 70% 阈值，触发 `smart_compress_turn`。

这修复了"一次大的 str_replace % 跳到超限"的漏洞。

## 关键设计决策

**为什么 FINALIZE 要求重新整合，而不是直接 cp？** 如果 DAG 中有"组装任务"（如 t9），它的产出可能包含编译错误或遗漏。FINALIZE 让主 Agent 有机会审视全局，产出干净的交付物。

**为什么 Worker 最多 15 步，Reviewer 最多 10 步？** Worker 需要搜索、阅读、写作，15 步足够完成一个聚焦的子任务。Reviewer 只需要 ls + read + 判断，10 步绰绰有余。步数过多会浪费 token。

**为什么依赖注入收集所有祖先而不只是直接依赖？** 传递依赖。如果 t3 依赖 t2，t2 依赖 t1，t3 需要同时看到 t1 和 t2 的产出才能完成工作。

**为什么 `_task_workers/` 在 FINALIZE 时设为只读？** 防止主 Agent 在整合时意外修改 Worker 的原始产出。Worker 产出是归档记录，应该保持不变。

## 相关文件

- `agent/tools/task_tools.py` — TaskProposeTool、TaskBuildTool、TaskExecuteTool、TaskCommitTool
- `agent/task_agent.py` — TaskSession 状态管理
- `agent/scheduler/executor.py` — SDDExecutor（Worker→Reviewer 循环）
- `agent/scheduler/batch_runner.py` — BatchRunner（DAG 调度）
- `agent/scheduler/schema.py` — ResearchTask、TaskGraph 数据模型
- `agent/context.py` — FINALIZE prompt 定义
- `core/session.py` — overlay 写入重定向、写保护
- `agent/tools/academic/latex_tool.py` — LaTeX 编译与引擎检测
