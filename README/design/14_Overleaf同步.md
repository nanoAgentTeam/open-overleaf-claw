# Overleaf 同步设计

## 设计目标

让 Bot 的本地修改能同步到 Overleaf，也能从 Overleaf 拉取合作者的修改。实现本地 Agent 工作流和 Overleaf 在线编辑的双向打通。

## 关联流程

一个项目关联 Overleaf 有两种方式：

### 创建新项目并关联
1. 在 Default 中创建本地项目
2. 在 Overleaf 上创建同名项目（通过 API）
3. 将 Overleaf 项目 ID 写入 project.yaml

### 关联已有 Overleaf 项目
1. 列出 Overleaf 上的项目列表
2. 选择目标项目，拿到 ID
3. 下载项目文件到本地 core 目录
4. 将 ID 写入 project.yaml

实际使用中，用自然语言告诉 Bot 就行，Bot 会自动完成这些步骤。

## Pull（拉取）

从 Overleaf 下载文件到本地 core：

- 下载项目 ZIP 包并解压
- 对比本地文件和下载的文件
- 本地有修改的文件不覆盖（防止丢失本地改动）
- 新文件和未修改的文件正常更新

触发方式：切换进入项目时自动触发（如果配置了 `auto_pull_before_work`），或手动 `/sync pull`。

## Push（推送）

将本地变更上传到 Overleaf：

- 对比本地文件和上次同步时的记录（通过 `.overleaf.json` 中的 mtime）
- 检测新增、修改、删除的文件
- 逐个上传/删除

触发方式：手动 `/sync push`。

## 元数据追踪

`.overleaf.json` 文件记录同步状态：

- 每个文件的 Overleaf file ID
- 每个文件上次同步时的 mtime
- Overleaf project ID

通过对比当前 mtime 和记录的 mtime，判断哪些文件有变更。

## 认证

使用 `.olauth` 文件存储 Overleaf 的登录 Cookie。通过 `ols login` 命令生成。

搜索路径：`.bot_data/.olauth` → workspace 目录 → 用户 home 目录。

## 当前状态

Pull & Push 功能尚未完整验证，可能存在边界情况需要处理。

## 关键设计决策

**为什么用 mtime 而不是文件 hash 来检测变更？** 简单高效。mtime 不需要读取文件内容，对大文件友好。

**为什么 Pull 不覆盖本地修改的文件？** 防止数据丢失。如果 Bot 刚修改了 main.tex，Pull 不应该用 Overleaf 上的旧版本覆盖它。

## 相关文件

- `agent/tools/overleaf.py` — Overleaf 工具实现
- `agent/tools/academic/__init__.py` — 学术工具包
