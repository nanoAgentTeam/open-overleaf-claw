# 工作空间与 Session

## 两个空间：Default 与 Project

系统有两个工作空间，分别承担不同职责：

| | Default（大厅） | Project（工作间） |
|---|---------|---------|
| 用途 | 聊天、浏览项目列表、创建/链接项目 | 在具体项目中工作 |
| 可用工具 | 项目管理、Overleaf 列表/创建、通用工具 | 文件读写、LaTeX 编译、Bash、SubAgent 等 |
| 文件操作 | 不直接操作项目文件 | 直接读写 core 目录中的文件 |

启动后默认在 Default。告诉 Bot "切换到 xxx 项目" 即可进入对应的 Project 工作空间。

## Workspace 目录结构

```
workspace/
├── Default/                    # 默认工作区（聊天、项目管理）
│   └── cli:default/            # CLI 默认 session
├── MyPaper/                    # 一个论文项目
│   ├── project.yaml            # 项目配置（git、overleaf、latex）
│   ├── MyPaper/                # core 目录（实际的论文文件）
│   │   ├── .git/
│   │   ├── main.tex
│   │   ├── references.bib
│   │   └── ...
│   ├── 0217_01/                # session（MMDD_NN 格式）
│   │   ├── .bot/               # session 元数据、对话历史
│   │   ├── artifacts/
│   │   └── subagents/          # 子 Agent 工作目录（overlay）
│   └── 0217_02/                # 另一个 session
└── AnotherPaper/
```

关键概念：

- **core 目录**：`workspace/{项目名}/{项目名}/`，存放论文的实际文件（.tex、.bib 等），是一个独立的 Git 仓库。Agent 进入项目后，工作目录就是这个 core。
- **session 目录**：`workspace/{项目名}/{MMDD_NN}/`，每次进入项目时创建，隔离对话历史和子 Agent 工作区。

## Session（会话）

每次 switch 进入项目时会创建一个新的 session（格式 `MMDD_NN`，如 `0217_01`）。Session 隔离了：

- 对话历史（每个 session 有独立的 history）
- 子 Agent 工作目录
- 元数据和 trace 日志

也可以传入已有的 session 名称来恢复之前的工作，不一定每次都新建。

## 进入工作区的方式

1. 启动 CLI 后，你在 Default
2. 用自然语言说"切换到 xxx 项目"，或"创建一个新项目"
3. Bot 执行 project_manager 工具完成切换
4. 切换后，提示符会变化，显示当前项目和 session 名称
5. 用 `/back` 可以返回 Default
