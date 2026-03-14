<div align="center">

# Open Overleaf Claw

**AI-Powered Academic Writing Agent System**

An open-source, multi-agent system for academic paper writing — manage LaTeX projects through natural language, with Overleaf sync, Git version control, and multi-channel IM integration.

一个开源的学术论文写作 AI Agent 系统 — 通过自然语言管理 LaTeX 项目，支持 Overleaf 同步、Git 版本控制和多渠道 IM 集成。

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<!-- TODO: Add demo GIF / video here -->
<!-- ![Demo](docs/assets/demo.gif) -->

[English](#english) · [中文](#中文)

</div>

---

# English

## Why Open Overleaf Claw?

Academic writing involves far more than just typing — literature search, LaTeX debugging, version control, Overleaf collaboration, template compliance, and formatting checks. Open Overleaf Claw wraps all of this into a single conversational interface:

- **Talk, don't click.** Create projects, write sections, search papers, compile PDFs — all through natural language.
- **Multi-Agent collaboration.** Delegate research, writing, and review to specialized sub-agents that work in isolated sandboxes.
- **Overleaf in the loop.** Bidirectional sync — pull from Overleaf, edit locally with AI, push back.
- **Never lose work.** Every AI edit is auto-committed to Git. Roll back any change in seconds.
- **Work from anywhere.** CLI at your desk, Feishu/Telegram/QQ/DingTalk on the go, Web UI for configuration.

<!-- TODO: Add architecture overview diagram here -->
<!-- ![Architecture](docs/assets/architecture.png) -->

## Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Conversational LaTeX Editing** | Read, write, and refactor `.tex` / `.bib` files through chat |
| **LaTeX Compilation** | One-command PDF build with error diagnosis and auto-fix |
| **Overleaf Sync** | Pull & push files to/from Overleaf — no browser needed |
| **Git Version Control** | Auto-commit every edit, interactive history, one-click rollback |
| **Literature Search** | arXiv, PubMed, OpenAlex, Semantic Scholar — with full-text PDF reading |
| **Venue Compliance** | Built-in skills for NeurIPS, ICML, ICLR, AAAI, ACL, CVPR and more |

### Agent System

| Feature | Description |
|---------|-------------|
| **Multi-Agent Collaboration** | Main agent delegates to specialized workers (researcher, writer, reviewer) |
| **Sandbox Isolation** | Sub-agents work in overlay directories — no accidental overwrites |
| **Task Mode (SDD)** | Decompose complex tasks into a DAG, execute in parallel batches |
| **Research Radar** | Automated literature monitoring on a schedule |

### Integration & Access

| Feature | Description |
|---------|-------------|
| **CLI** | Full-featured interactive terminal |
| **Web UI** | Browser-based dashboard for configuration and monitoring |
| **Feishu (Lark)** | WebSocket — no public IP required |
| **Telegram** | Long-polling bot |
| **QQ / DingTalk** | Native bot integration |
| **Push Notifications** | Automation results delivered to any channel |

## Quick Start

### 1. Install

```bash
git clone https://github.com/your-org/open_overleaf_claw.git
cd open_overleaf_claw

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

Copy the default config and add your LLM API key:

```bash
cp settings.default.json settings.json
```

Edit `settings.json` — add at least one LLM provider:

```json
{
  "provider": {
    "activeId": "my-llm",
    "instances": [
      {
        "id": "my-llm",
        "provider": "openai",
        "modelName": "gpt-4o",
        "apiKey": "sk-your-key-here",
        "apiBase": "https://api.openai.com/v1",
        "enabled": true
      }
    ]
  }
}
```

Any OpenAI-compatible API works (DeepSeek, Qwen, StepFun, etc.) — just change `apiBase` and `modelName`.

### 3. Launch

**CLI mode** — interactive terminal:

```bash
python cli/main.py agent
```

**Gateway mode** — Web UI + IM bots:

```bash
python cli/main.py gateway --port 18790
# Open http://localhost:18790 in your browser
```

### 4. (Optional) Overleaf Sync

```bash
pip install overleaf-sync
ols login          # Generates .olauth cookie file
```

<!-- TODO: Add screenshot of CLI session here -->
<!-- ![CLI Session](docs/assets/cli-session.png) -->

## Usage

### Workspace Concept

```
workspace/
├── Default/                    # Lobby — project management & general chat
└── MyPaper/                    # A paper project
    ├── project.yaml            # Project config (Git, Overleaf, LaTeX engine)
    ├── MyPaper/                # "core" directory (actual LaTeX files + Git repo)
    │   ├── main.tex
    │   ├── references.bib
    │   └── ...
    └── 0314_01/                # Session directory (conversation history, sub-agent workspace)
```

- **Default space**: Create, list, and switch between projects.
- **Project space**: Edit files, compile, search papers, manage Git — all tools available.

### Typical Workflow

```
You: Create a paper project called "MoE-Survey" and link it to Overleaf
Bot: ✅ Project created, Overleaf linked, switched to MoE-Survey.

You: Research the latest MoE papers and write an introduction
Bot: 🔎 [arXiv search]... 📝 [writing intro]... ✅ Compilation passed.

You: /sync push
Bot: ✅ Pushed 3 files to Overleaf.

You: /git
Git> Show me recent changes
Git> Undo the last commit
Git> /done
```

### Commands

| Command | Description |
|---------|-------------|
| `/task <goal>` | Enter Task Mode — decompose & execute complex goals |
| `/compile` | Compile LaTeX to PDF |
| `/sync pull` | Pull latest files from Overleaf |
| `/sync push` | Push local changes to Overleaf |
| `/git` | Enter interactive Git management |
| `/reset` | Reset current session (clear history) |
| `/back` | Return to Default space |
| `/done` | Exit current mode (Task / Git) |

### Task Mode

For complex, multi-step goals, Task Mode decomposes work into a DAG of sub-tasks:

```
You: /task Write a complete survey on Mixture-of-Experts

Phase 1 — UNDERSTAND: Bot reads your project files
Phase 2 — PROPOSE: Bot generates a proposal for your review
Phase 3 — PLAN: Bot builds a task graph (DAG) for confirmation
Phase 4 — EXECUTE: Sub-agents run tasks in parallel batches
Phase 5 — FINALIZE: Bot merges outputs and commits
→ Auto-exits task mode when complete
```

<!-- TODO: Add Task Mode flowchart or screenshot here -->
<!-- ![Task Mode](docs/assets/task-mode.png) -->

### Web UI

The Gateway mode serves a browser-based dashboard at `http://localhost:18790`:

- **Dashboard** — System status, active model, workspace overview
- **Provider Management** — Add/edit LLM instances, test connections
- **Channel Accounts** — Configure IM bot credentials
- **Automation** — Scheduled tasks per project (cron-based)
- **Push Subscriptions** — Route notifications to any channel
- **Live Logs** — Real-time WebSocket log stream

<!-- TODO: Add Web UI screenshot here -->
<!-- ![Web UI](docs/assets/webui.png) -->

### IM Integration

Configure channels in `settings.json` or through the Web UI:

| Platform | Connection | Public IP Required |
|----------|-----------|-------------------|
| Feishu (Lark) | WebSocket | No |
| Telegram | Long-polling | No |
| QQ | Bot API | No |
| DingTalk | Stream | No |

For step-by-step setup guides, see:
- [Feishu Setup Guide](README/im配置与推送/feishu_ZH.md)
- [Telegram Setup Guide](README/im配置与推送/Telegram_ZH.md)
- [QQ Bot Setup Guide](README/im配置与推送/QQBot_ZH.md)
- [DingTalk Setup Guide](README/im配置与推送/DingTalk_ZH.md)

## Configuration

All runtime configuration lives in a single `settings.json` file (template: `settings.default.json`).

| Section | Purpose |
|---------|---------|
| `provider.instances` | LLM providers (API key, base URL, model name) |
| `channel.accounts` | IM bot credentials |
| `gateway` | Web UI host & port |
| `features` | Toggle history, memory, auto-summarize, etc. |
| `tools` | Web search API key, academic tool keys |
| `pushSubscriptions` | Automation notification routing |

Other config files:

| File | Purpose |
|------|---------|
| `config/tools.json` | Tool registry (class paths, args, permissions) |
| `config/commands.json` | Slash command definitions |
| `config/agent_profiles/` | Agent role profiles (available tools per role) |
| `workspace/{project}/project.yaml` | Per-project settings (Overleaf ID, LaTeX engine, Git) |

For full configuration documentation, see [Configuration Guide](README/guide/08_配置与快速开始.md).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Channels: CLI / Feishu / Telegram / QQ / DingTalk      │
└──────────────────────┬──────────────────────────────────┘
                       │ InboundMessage / OutboundMessage
                 ┌─────▼─────┐
                 │ MessageBus │
                 └─────┬─────┘
                       │
              ┌────────▼────────┐
              │   AgentLoop     │ ← CommandRouter (slash commands)
              │  (Main Agent)   │ ← ContextManager (prompt assembly)
              └──┬──────────┬───┘
                 │          │
     ┌───────────▼──┐  ┌───▼──────────┐
     │ ToolRegistry │  │  SubAgents   │
     │ (40+ tools)  │  │  (Workers)   │
     └──────┬───────┘  └──────────────┘
            │
  ┌─────────┼─────────────────────┐
  │         │                     │
  ▼         ▼                     ▼
Project   LLM Provider        Automation
(Git,     (OpenAI-compat,     (APScheduler,
 LaTeX,    hot-swappable)      cron jobs)
 Overleaf)
```

For detailed design docs, see the [Design Documents](README/design/).

## Documentation

### Guides
- [Project Overview](README/guide/01_项目概览.md)
- [Workspace & Sessions](README/guide/02_工作空间与Session.md)
- [Agent Collaboration](README/guide/03_Agent协作.md)
- [Isolation & Security](README/guide/04_项目隔离与安全.md)
- [Git Management](README/guide/05_Git版本管理.md)
- [Overleaf Sync](README/guide/06_Overleaf同步.md)
- [Usage Guide](README/guide/07_使用指南.md)
- [Configuration & Quick Start](README/guide/08_配置与快速开始.md)
- [Web UI Guide](README/guide/09_Web界面功能说明.md)

### Design Documents
- [AgentLoop](README/design/03_AgentLoop.md) · [Tool System](README/design/08_Tool_System.md) · [Task Mode](README/design/17_Task_Mode.md) · [Memory System](README/design/06_Memory.md) · [more →](README/design/)

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

# 中文

## 为什么选择 Open Overleaf Claw？

学术写作远不止打字 — 文献检索、LaTeX 调试、版本控制、Overleaf 协作、模板合规、格式检查……Open Overleaf Claw 把这一切整合到一个对话界面中：

- **说话代替点击。** 创建项目、撰写章节、搜索文献、编译 PDF — 全部通过自然语言完成。
- **多 Agent 协作。** 将调研、写作、审阅委派给专门的子 Agent，它们在隔离沙箱中工作。
- **Overleaf 同步。** 双向同步 — 从 Overleaf 拉取、本地 AI 编辑、推送回去。
- **永不丢失工作。** 每次 AI 编辑自动 Git 提交，几秒内回滚任何变更。
- **随时随地工作。** 桌面用 CLI，移动端用飞书 / Telegram / QQ / 钉钉，配置用 Web UI。

<!-- TODO: 在此添加架构总览图 -->
<!-- ![Architecture](docs/assets/architecture.png) -->

## 功能特性

### 核心能力

| 功能 | 说明 |
|------|------|
| **对话式 LaTeX 编辑** | 通过聊天读写和重构 `.tex` / `.bib` 文件 |
| **LaTeX 编译** | 一键 PDF 构建，自动诊断并修复错误 |
| **Overleaf 同步** | 与 Overleaf 双向拉取和推送文件 — 无需浏览器 |
| **Git 版本控制** | 每次编辑自动提交，交互式历史查看，一键回滚 |
| **文献检索** | arXiv、PubMed、OpenAlex、Semantic Scholar — 支持 PDF 全文阅读 |
| **会议模板合规** | 内置 NeurIPS、ICML、ICLR、AAAI、ACL、CVPR 等会议 Skill |

### Agent 系统

| 功能 | 说明 |
|------|------|
| **多 Agent 协作** | 主 Agent 委派任务给专门的 Worker（调研员、写作者、审阅员） |
| **沙箱隔离** | 子 Agent 在 overlay 目录中工作 — 不会意外覆盖文件 |
| **Task 模式 (SDD)** | 将复杂任务分解为 DAG，按批并行执行 |
| **研究雷达** | 按计划自动化文献监控 |

### 集成与访问

| 功能 | 说明 |
|------|------|
| **CLI** | 全功能交互式终端 |
| **Web UI** | 浏览器端仪表盘，用于配置和监控 |
| **飞书** | WebSocket 连接 — 无需公网 IP |
| **Telegram** | 长轮询机器人 |
| **QQ / 钉钉** | 原生机器人集成 |
| **推送通知** | 自动化结果投递到任意渠道 |

## 快速开始

### 1. 安装

```bash
git clone https://github.com/your-org/open_overleaf_claw.git
cd open_overleaf_claw

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

复制默认配置并添加你的 LLM API Key：

```bash
cp settings.default.json settings.json
```

编辑 `settings.json` — 至少添加一个 LLM 提供商：

```json
{
  "provider": {
    "activeId": "my-llm",
    "instances": [
      {
        "id": "my-llm",
        "provider": "openai",
        "modelName": "gpt-4o",
        "apiKey": "sk-your-key-here",
        "apiBase": "https://api.openai.com/v1",
        "enabled": true
      }
    ]
  }
}
```

任何 OpenAI 兼容的 API 均可使用（DeepSeek、Qwen 通义千问、阶跃星辰等）— 只需修改 `apiBase` 和 `modelName`。

### 3. 启动

**CLI 模式** — 交互式终端：

```bash
python cli/main.py agent
```

**Gateway 模式** — Web UI + IM 机器人：

```bash
python cli/main.py gateway --port 18790
# 浏览器打开 http://localhost:18790
```

### 4.（可选）Overleaf 同步

```bash
pip install overleaf-sync
ols login          # 生成 .olauth 认证文件
```

<!-- TODO: 在此添加 CLI 会话截图 -->
<!-- ![CLI Session](docs/assets/cli-session.png) -->

## 使用说明

### 工作区概念

```
workspace/
├── Default/                    # 大厅 — 项目管理和通用聊天
└── MyPaper/                    # 一个论文项目
    ├── project.yaml            # 项目配置（Git、Overleaf、LaTeX 引擎）
    ├── MyPaper/                # "core" 目录（实际的 LaTeX 文件 + Git 仓库）
    │   ├── main.tex
    │   ├── references.bib
    │   └── ...
    └── 0314_01/                # Session 目录（对话历史、子 Agent 工作区）
```

- **Default 空间**：创建、列出和切换项目。
- **Project 空间**：编辑文件、编译、搜索文献、管理 Git — 全部工具可用。

### 典型工作流

```
You: 创建一个叫 "MoE-Survey" 的论文项目，并关联 Overleaf
Bot: ✅ 项目已创建，Overleaf 已关联，已切换到 MoE-Survey。

You: 调研最新的 MoE 论文并写一个 Introduction
Bot: 🔎 [arXiv 搜索]... 📝 [撰写 Introduction]... ✅ 编译通过。

You: /sync push
Bot: ✅ 已推送 3 个文件到 Overleaf。

You: /git
Git> 最近做了什么改动
Git> 回退上一次提交
Git> /done
```

### 命令一览

| 命令 | 说明 |
|------|------|
| `/task <目标>` | 进入 Task 模式 — 分解并执行复杂目标 |
| `/compile` | 编译 LaTeX 生成 PDF |
| `/sync pull` | 从 Overleaf 拉取最新文件 |
| `/sync push` | 推送本地修改到 Overleaf |
| `/git` | 进入交互式 Git 管理 |
| `/reset` | 重置当前 Session（清空对话历史） |
| `/back` | 返回 Default 空间 |
| `/done` | 退出当前模式（Task / Git） |

### Task 模式

面对复杂的多步骤目标，Task 模式将工作分解为子任务 DAG：

```
You: /task 写一篇关于 Mixture-of-Experts 的完整综述

阶段 1 — UNDERSTAND：Bot 阅读项目文件，理解上下文
阶段 2 — PROPOSE：Bot 生成方案供你审阅
阶段 3 — PLAN：Bot 构建任务图（DAG），等待你确认
阶段 4 — EXECUTE：子 Agent 按批并行执行任务
阶段 5 — FINALIZE：Bot 合并产出并提交
→ 完成后自动退出 Task 模式
```

<!-- TODO: 在此添加 Task 模式流程图或截图 -->
<!-- ![Task Mode](docs/assets/task-mode.png) -->

### Web UI

Gateway 模式在 `http://localhost:18790` 提供浏览器端仪表盘：

- **控制中心** — 系统状态、当前模型、工作区概览
- **模型管理** — 添加/编辑 LLM 实例，测试连接
- **通讯账号** — 配置 IM 机器人凭证
- **自动化任务** — 按项目配置定时任务（cron 表达式）
- **推送订阅** — 将通知路由到任意渠道
- **实时日志** — WebSocket 实时日志流

<!-- TODO: 在此添加 Web UI 截图 -->
<!-- ![Web UI](docs/assets/webui.png) -->

### IM 集成

通过 `settings.json` 或 Web UI 配置渠道：

| 平台 | 连接方式 | 需要公网 IP |
|------|----------|------------|
| 飞书 | WebSocket | 否 |
| Telegram | 长轮询 | 否 |
| QQ | Bot API | 否 |
| 钉钉 | Stream | 否 |

详细配置指南：
- [飞书配置指南](README/im配置与推送/feishu_ZH.md)
- [Telegram 配置指南](README/im配置与推送/Telegram_ZH.md)
- [QQ Bot 配置指南](README/im配置与推送/QQBot_ZH.md)
- [钉钉配置指南](README/im配置与推送/DingTalk_ZH.md)

## 配置说明

所有运行时配置集中在 `settings.json` 文件中（模板：`settings.default.json`）。

| 配置段 | 用途 |
|--------|------|
| `provider.instances` | LLM 提供商（API Key、Base URL、模型名） |
| `channel.accounts` | IM 机器人凭证 |
| `gateway` | Web UI 主机和端口 |
| `features` | 开关：历史、记忆、自动摘要等 |
| `tools` | Web 搜索 API Key、学术工具 Key |
| `pushSubscriptions` | 自动化通知路由 |

其他配置文件：

| 文件 | 用途 |
|------|------|
| `config/tools.json` | 工具注册表（class 路径、参数、权限） |
| `config/commands.json` | 斜杠命令定义 |
| `config/agent_profiles/` | Agent 角色 Profile（各角色可用工具） |
| `workspace/{项目}/project.yaml` | 项目级配置（Overleaf ID、LaTeX 引擎、Git） |

完整配置文档请参考[配置与快速开始指南](README/guide/08_配置与快速开始.md)。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  渠道层: CLI / 飞书 / Telegram / QQ / 钉钉              │
└──────────────────────┬──────────────────────────────────┘
                       │ InboundMessage / OutboundMessage
                 ┌─────▼─────┐
                 │ MessageBus │
                 └─────┬─────┘
                       │
              ┌────────▼────────┐
              │   AgentLoop     │ ← CommandRouter（斜杠命令）
              │   （主 Agent）   │ ← ContextManager（Prompt 组装）
              └──┬──────────┬───┘
                 │          │
     ┌───────────▼──┐  ┌───▼──────────┐
     │ ToolRegistry │  │  SubAgents   │
     │  （40+ 工具） │  │ （Worker）    │
     └──────┬───────┘  └──────────────┘
            │
  ┌─────────┼─────────────────────┐
  │         │                     │
  ▼         ▼                     ▼
Project   LLM Provider        Automation
(Git,     (OpenAI 兼容,        (APScheduler,
 LaTeX,    热切换)               定时任务)
 Overleaf)
```

详细设计文档请参考[设计文档目录](README/design/)。

## 文档导航

### 使用指南
- [项目概览](README/guide/01_项目概览.md)
- [工作空间与 Session](README/guide/02_工作空间与Session.md)
- [Agent 协作](README/guide/03_Agent协作.md)
- [项目隔离与安全](README/guide/04_项目隔离与安全.md)
- [Git 版本管理](README/guide/05_Git版本管理.md)
- [Overleaf 同步](README/guide/06_Overleaf同步.md)
- [使用指南](README/guide/07_使用指南.md)
- [配置与快速开始](README/guide/08_配置与快速开始.md)
- [Web 界面功能说明](README/guide/09_Web界面功能说明.md)

### 设计文档
- [AgentLoop](README/design/03_AgentLoop.md) · [工具系统](README/design/08_Tool_System.md) · [Task 模式](README/design/17_Task_Mode.md) · [记忆系统](README/design/06_Memory.md) · [更多 →](README/design/)

## 参与贡献

欢迎贡献！请随时提交 Issue 和 Pull Request。

## 许可证

本项目基于 MIT 许可证开源 — 详见 [LICENSE](LICENSE) 文件。
