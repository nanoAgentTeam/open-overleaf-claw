# Memory 设计

## 什么是 Memory

Memory 是 Agent 的长期记忆系统。与 History（对话历史）不同，Memory 存储的是提炼后的知识——用户偏好、项目关键信息、跨 session 的经验。

## 记忆层次

系统有多层记忆，作用范围不同：

### 1. Session 内记忆（短期）
就是当前 session 的对话历史和 auto-summary。只在当前 session 中有效。

### 2. 项目记忆（中期）
存储在 `workspace/{项目名}/.project_memory/` 下。跨 session 共享，但只属于当前项目。

比如：这个论文的核心论点是什么、reviewer 提了哪些意见、上次修改到哪里了。

### 3. 全局记忆（长期）
存储在全局的 `MEMORY.md` 中。跨项目共享。

比如：用户偏好用什么引用格式、习惯的写作风格、常用的 LaTeX 模板。

### 4. Active Context（活跃上下文）
存储在 `active_context.md` 中。是 auto-summary 的产物，记录当前工作的关键上下文。

每次组装 system prompt 时，active_context 会被注入，让 Agent 知道"之前在做什么"。

## 记忆的读写

Agent 通过两个工具操作记忆：

- **save_memory**：将信息写入 MEMORY.md 或 active_context.md
- **retrieve_memory**：读取记忆内容

这两个工具只有 Assistant 角色可以使用，Worker 不能修改记忆。

## Memory Protocol

System prompt 中包含 Memory Protocol，告诉 Agent：
- 什么时候应该保存记忆（发现重要信息、用户表达偏好时）
- 什么时候应该读取记忆（开始新任务、需要回忆上下文时）
- 记忆的格式规范

## 关键设计决策

**为什么分多层？** 不同信息的生命周期不同。论文的具体修改细节只在当前 session 有意义，但用户的写作偏好应该永久保留。

**为什么用文件而不是数据库？** 可读性。MEMORY.md 就是一个 Markdown 文件，用户可以直接查看和编辑。

**为什么只有 Assistant 能写记忆？** 防止子 Agent 写入不准确的信息污染长期记忆。

## 相关文件

- `agent/context.py` — 记忆注入逻辑
- `agent/tools/memory.py` — save_memory / retrieve_memory 工具
- `config/vfs.json` — 记忆文件路径配置
