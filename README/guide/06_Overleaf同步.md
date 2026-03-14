# Overleaf 同步

## 关联 Overleaf 项目

在 Default 中，你可以：

- 创建新项目并同时在 Overleaf 上创建，自动关联
- 关联已有的 Overleaf 项目：先列出 Overleaf 项目列表，拿到 ID 后关联

实际使用中，用自然语言告诉 Bot 就行，比如"创建一个论文项目并关联 Overleaf"，Bot 会自动完成所有步骤。

## Pull & Push（尚未完整验证）

| 操作 | 触发方式 | 说明 |
|------|----------|------|
| Pull | switch 时自动触发 / `/sync pull` | 从 Overleaf 下载最新文件，本地有修改的文件不覆盖 |
| Push | `/sync push` | 将本地变更推送到 Overleaf（新增、修改、删除） |

Pull/Push 的行为在 `project.yaml` 中配置，包括 Overleaf 项目 ID 和是否自动 pull。

## 认证

需要 `.olauth` 文件（Overleaf 登录 Cookie）。通过 `ols login` 命令生成，放在 `.bot_data/.olauth` 或项目根目录。
