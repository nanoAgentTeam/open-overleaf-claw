# Git 版本管理

每个项目的 core 目录是一个独立的 Git 仓库。

## Auto Commit

当 `project.yaml` 中配置了 `git.auto_commit: true` 时，每个 turn 结束后自动提交所有写入的文件。Commit message 格式：`[bot] Edit main.tex, references.bib`。

这意味着你可以随时回退到任意一次修改，不用担心 Bot 的改动丢失。

## Git Agent（/git）

输入 `/git` 进入交互式 Git 管理子会话，用自然语言管理版本：

```
[moe:0217_01] You: /git
🔧 [Git 模式] 进入版本管理。

[Git] You: 最近做了什么改动
[Git] 🤖 （展示提交记录）

[Git] You: 回到 sync 那个提交
[Git] 🤖 （展示影响范围，等待确认后执行回退）

[Git] You: /done
🔧 退出 Git 模式。[回退了 2 个提交]
```

可用操作：查看历史、查看状态、查看 diff、回退 commit、恢复文件、丢弃未提交修改。

破坏性操作（回退、丢弃）必须先展示影响范围，等用户确认后才执行。
