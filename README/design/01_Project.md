# Project 设计

## 什么是 Project

Project 是系统中最核心的一级抽象。每个论文对应一个 Project，它封装了论文的所有文件、Git 仓库、Overleaf 关联、LaTeX 编译配置。

系统中有一个特殊的 Project 叫 Default，它不是论文项目，而是"大厅"——用来聊天、浏览项目列表、创建和管理项目。

## 目录结构

每个 Project 在 workspace 下有一个同名目录：

```
workspace/MyPaper/
├── project.yaml            # 项目配置
├── MyPaper/                # core 目录（论文实际文件）
│   ├── .git/
│   ├── main.tex
│   ├── references.bib
│   └── ...
├── .project_memory/        # 跨 session 的项目记忆
├── 0217_01/                # session 目录
├── 0217_02/
└── ...
```

核心概念是 **core 目录**（`workspace/{项目名}/{项目名}/`）。这是论文文件的实际存放位置，也是一个独立的 Git 仓库。Agent 进入项目后，所有文件操作都以 core 为根目录。

## project.yaml

每个项目的配置文件，定义了：

- Git 配置：是否启用 auto_commit
- Overleaf 配置：project_id、是否自动 pull
- LaTeX 配置：编译命令、主文件路径

这个文件在项目创建时自动生成，也可以手动修改。

## 项目的生命周期

1. **创建**：在 Default 中通过 project_manager 工具创建，生成目录结构和 project.yaml
2. **关联 Overleaf**（可选）：创建或关联已有的 Overleaf 项目
3. **切换进入**：从 Default 切换到项目，创建新 session，自动 pull Overleaf（如果配置了）
4. **工作**：在项目中读写文件、编译、调用子 Agent
5. **返回**：用 `/back` 回到 Default

## 关键设计决策

**为什么 core 目录和项目目录同名嵌套？** 因为项目目录下还需要放 session 目录、project.yaml、项目记忆等。core 是"论文本身"，项目目录是"围绕论文的一切"。这样 core 可以是一个干净的 Git 仓库，不会混入 bot 的元数据。

**为什么每个项目是独立的 Git 仓库？** 每个论文的版本历史应该独立。auto commit 会产生大量提交，不应该污染其他项目。

## 相关文件

- `core/project.py` — Project 类的实现
- `agent/tools/project.py` — project_manager 工具
- `config/agents.json` — 项目级 agent 配置
