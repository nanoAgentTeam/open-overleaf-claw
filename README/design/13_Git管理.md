# Git 管理设计

## 设计目标

让用户不用担心 Bot 改坏论文。每次修改都有记录，随时可以回退。

## Auto Commit

当 `project.yaml` 中配置了 `git.auto_commit: true`：

- 每次 Agent 通过 write_file 写入文件时，文件路径被记录到 pending_writes 列表
- 当前 turn（一轮对话）结束时，所有 pending_writes 被统一 git add + commit
- Commit message 格式：`[bot] Edit main.tex, references.bib`

这意味着每一轮对话的修改都是一个独立的 commit，可以精确回退。

## Git Agent

`/git` 命令会启动一个专门的 Git 管理子会话。Git Agent 拥有 GitAgent 角色，具备 Git 操作权限。

可用操作：

| 操作 | 说明 | 是否破坏性 |
|------|------|-----------|
| git_history | 查看提交记录 | 否 |
| git_status | 查看工作区状态 | 否 |
| git_diff | 查看变更内容 | 否 |
| git_undo | 回退到指定 commit | 是 |
| git_restore_file | 恢复指定文件到某个版本 | 是 |
| git_discard | 丢弃未提交的修改 | 是 |

### 破坏性操作确认

所有破坏性操作都遵循两步流程：

1. 先展示影响范围（会丢失哪些 commit、哪些文件会被改变）
2. 等待用户明确确认后才执行

Git Agent 子会话用 `/done` 退出，退出时会生成操作摘要记录到主 Agent 的历史中。

## 关键设计决策

**为什么 auto commit 在 turn 结束时而不是每次写入时？** 一轮对话中 Agent 可能多次写入同一个文件（比如先写再修改），turn 结束时统一提交更干净，一个 commit 对应一轮完整的修改。

**为什么 Git 操作要独立成子会话？** 关注点分离。Git 操作（特别是回退）需要专注的交互，不应该和论文写作混在一起。独立子会话也让 Git Agent 有专门的工具集和权限。

## 相关文件

- `core/project.py` — auto commit 和 GitRepo 实现
- `agent/git_agent.py` — Git Agent 子会话
