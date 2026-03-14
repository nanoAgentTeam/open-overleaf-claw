# Tool System 设计

## 什么是 Tool System

Tool System 是 Agent 与外部世界交互的桥梁。Agent 本身只能思考和生成文本，所有实际操作（读写文件、编译 LaTeX、搜索论文、调用 Bash）都通过工具完成。

## 工具注册

所有工具在 `config/tools.json` 中声明式注册：

每个工具定义包含：
- **class**：Python 类路径
- **enabled**：是否启用（`false` 时全局禁用，任何 profile 都无法加载）
- **args**：构造参数，支持模板变量注入

## 动态过滤

Agent 在不同上下文中看到的工具列表是不同的。ToolLoader 根据 profile 的 `tools[]` 列表筛选：

1. 从 `tools.json` 中加载所有 `enabled: true` 的工具
2. 只保留当前 profile 声明的工具
3. 项目级 `tools_blacklist` 可进一步过滤

## ToolContext 注入

工具在实例化时会收到 ToolContext，包含当前的运行时信息：

- 当前项目和 session
- 文件路径解析方法
- 写入目标（core 还是 overlay）

这让工具能够感知当前上下文，而不需要硬编码路径。

## 工具分类

| 类别 | 工具 | 说明 |
|------|------|------|
| 文件操作 | read_file、write_file、str_replace | 基础文件读写 |
| 执行 | bash | Shell 命令执行（Worker 在 overlay 内，Assistant 在 core 内） |
| 学术 | arxiv_search、latex_compile | 论文搜索和编译 |
| 同步 | overleaf | Overleaf 同步（仅 chat_mode） |
| 网络 | web_fetch、web_search | 网页获取和搜索 |
| 记忆 | memory_get、memory_search、memory_nav、memory_list、memory_write、memory_brief | 项目记忆读写 |
| 协作 | create_subagent、assign_task | 子 Agent 管理 |
| 调研 | task_planner | 启动 Deep Research |
| 项目 | project_manager | 项目管理（仅 chat_mode） |

### 已禁用工具（`enabled: false`）

| 工具 | 说明 |
|------|------|
| save_memory / retrieve_memory | 旧版记忆工具，已被 memory_* 系列替代，保留供后续使用 |
| browser_use | 浏览器自动化，暂时禁用，保留供后续使用 |

## Agent Profile 与工具分配

每个 agent 类型通过 profile 声明可用工具。详见 `README/design/22_Agent_Profile.md`。

当前工具分配：

| Tool | project_mode | automation | task_agent | chat_mode | sdd_worker | subagent | reviewer |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| read_file | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| write_file | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| str_replace | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| bash | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| web_fetch | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| web_search | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| arxiv_search | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| latex_compile | ✓ | ✓ | ✓ | | ✓ | ✓ | |
| overleaf | | | | ✓ | | | |
| project_manager | | | | ✓ | | | |
| create_subagent | ✓ | | | | | | |
| assign_task | ✓ | | | | | | |
| memory_* (6个) | ✓ | ✓ | | | | | |
| profile_read/refresh | ✓ | ✓ | | | | | |
| notify_push | ✓ | ✓ | | | | | |

## LaTeX 编译与 Overlay

`latex_compile` 工具在 Worker 模式下会在 overlay 内编译：

```python
# Worker: 编译 overlay 中的 .tex
tex_path = session.root / main_tex
result = project.compile_pdf_file(tex_path, cwd=session.root)

# Assistant: 编译 core 中的 .tex
result = project.compile_pdf()
```

`compile_pdf_file()` 和 `_compile()` 接受 `cwd` 参数，内部的 `subprocess.run` 和输出路径都使用 `cwd` 而非硬编码的 `self.core`。

## 关键设计决策

**为什么用 JSON 声明式注册而不是代码注册？** 可配置性。启用/禁用工具、调整权限不需要改代码，改 JSON 就行。

**为什么删除了 `ls` 工具？** Copy-on-Init 后，Worker 的 overlay 是完整工作目录，`bash ls` 在 overlay 内执行，行为与 `ls` 工具完全一致。`ls` 工具变成了 `bash ls` 的冗余封装，唯一区别是过滤隐藏目录，但 overlay 中不需要这个过滤。

**为什么工具并行执行？** LLM 经常一次请求多个工具调用（比如同时搜索 arXiv 和读取文件），并行执行节省时间。

## 相关文件

- `config/tools.json` — 工具注册表
- `config/agent_profiles/*.json` — 7 个 profile 定义
- `agent/tools/loader.py` — ToolLoader，负责 profile 加载和工具实例化
- `agent/tools/` — 各工具实现
