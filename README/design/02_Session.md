# Session 设计

## 什么是 Session

Session 是一次工作会话。每次你切换进入一个项目，系统会创建一个新的 Session（或恢复已有的）。Session 的命名格式是 `MMDD_NN`，比如 `0217_01` 表示 2 月 17 日的第一个 session。

Session 的核心职责是**隔离**：不同 session 之间的对话历史、子 Agent 工作区、元数据互不干扰。

## 目录结构

```
workspace/MyPaper/0217_01/
├── .bot/                   # session 元数据
│   ├── history.jsonl       # 对话历史
│   ├── events.jsonl        # 事件日志
│   └── ...
├── subagents/              # Swarm 子 Agent 的 overlay 目录
│   ├── researcher/
│   └── writer/
└── _task_workers/          # SDD Worker 的 overlay 目录
    ├── t1_r1/
    └── t2_r1/
```

Worker 的 overlay 目录包含 core 的完整副本（通过 `init_overlay()` 拷贝），Worker 在其中独立工作。

## Session 的生命周期

1. **创建**：切换项目时自动创建，分配 `MMDD_NN` 编号
2. **工作**：所有对话和操作都在当前 session 上下文中进行
3. **恢复**：可以传入已有的 session 名称恢复之前的工作，对话历史会被加载
4. **结束**：切换到其他项目或退出时，session 保留在磁盘上，随时可恢复

## 角色与路径解析

Session 根据角色（role_type）决定文件操作的行为：

- **Assistant（主 Agent）**：读写都直接指向 project core
- **Worker（子 Agent）**：创建时 `init_overlay()` 将 core 浅拷贝到 overlay，之后读写都在 overlay 内完成

Worker 的 `resolve()` 直接返回 overlay 路径，不再 fallback 到 core。这保证了 bash、read_file、latex_compile 等所有工具行为一致。

## Merge 机制

Worker 完成任务后，通过 `_diff_overlay()` 对比 overlay 和 core（SHA-256），只提取变更文件：

- `merge_to_core = true`：变更文件直接复制到 core，触发 auto commit
- `merge_to_core = false`（当前默认）：变更文件复制到 `core/_subagent_results/{agent_name}/`，供主 Agent 审阅
- `diff_only = true`：启用 diff-based merge（copy-on-init 模式下使用）

SDD Worker 的 merge 走 `executor._merge_worker_to_core()`，同样使用 `_diff_overlay()`，并跳过注入的依赖目录。

## 关键设计决策

**为什么用 Copy-on-Init 而不是透明 Overlay？** 旧模型中读时 fallback core、写时落 overlay，导致 `latex_compile` 看不到 Worker 修改、`bash ls` 和 `ls` 工具行为不一致。Copy-on-Init 后 overlay 是自包含的完整工作目录，所有工具行为统一。

**为什么不直接让子 Agent 写 core？** 安全性。子 Agent 可能产出质量不佳的内容，直接写入会污染论文。overlay + merge 的设计让主 Agent 有审阅的机会。

**为什么 session 用日期编号？** 直观。看到 `0217_01` 就知道是哪天的工作，不需要额外的命名。

## 相关文件

- `core/session.py` — Session 类的实现（init_overlay、_diff_overlay、resolve、write_target、merge_child）
- `config/agents.json` — merge_to_core 配置
