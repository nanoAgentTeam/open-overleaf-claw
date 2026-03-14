# Agent Profile 系统设计

## 背景：为什么需要 Profile

在旧架构中，`role_type`（"Assistant" / "Worker"）同时承担两个职责：

1. **决定工具集合**：`role_type.lower()` → 加载 `assistant.json` 或 `worker.json`
2. **控制文件权限**：Session 根据 role_type 决定写入 overlay 还是 core

这带来了几个问题：

- 只有 2 个 profile，无法区分 chat agent、project agent、SDD worker 等不同角色的工具需求
- SDD Worker/Reviewer 的工具是硬编码在 `_get_sandboxed_tools()` 里的，没走 profile 系统
- `role_type` 既是权限标识又是工具选择器，职责混淆

## 新架构：Profile 是唯一身份

```
profile（唯一标识）
  ├── tools[]        → 决定工具集合
  └── role_type      → 派生出来，只用于权限控制
```

`profile` 是 agent 的主要标识符。`role_type` 从 profile JSON 中派生，降级为内部属性。

## Profile 文件

每个 agent 类型对应一个 profile JSON，存放在 `config/agent_profiles/`：

```
config/agent_profiles/
├── chat_mode_agent.json          ← Default 项目 Q&A
├── project_mode_agent.json       ← 项目主控（完整工具集）
├── project_mode_subagent.json    ← 项目子 Agent（受限工具集）
├── automation_agent.json         ← 自动化任务
├── project_task_agent.json       ← Task 模式主控
├── sdd_worker.json               ← SDD Worker（沙箱化）
└── sdd_reviewer.json             ← SDD Reviewer（只读）
```

格式很简单：

```json
{
  "role_type": "Assistant",
  "description": "项目主控 Agent",
  "tools": ["read_file", "write_file", "bash", "arxiv_search", "..."]
}
```

## 谁用哪个 Profile

| 场景 | Profile | role_type | 说明 |
|------|---------|-----------|------|
| CLI 默认启动 | chat_mode_agent | Assistant | 通用问答，有 overleaf、project_manager |
| 进入项目 | project_mode_agent | Assistant | 完整工具集，有 create_subagent、assign_task |
| TaskTool 创建的子 agent | project_mode_subagent | Worker | 文件操作 + web + latex_compile |
| 自动化任务 | automation_agent | Assistant | 类似项目主控，无 subagent 工具 |
| /task 模式 | project_task_agent | Assistant | 基础工具 + latex，task 工具动态注册 |
| SDD Worker | sdd_worker | Worker | 沙箱化文件工具 + latex_compile |
| SDD Reviewer | sdd_reviewer | Worker | 只读工具（read_file + bash） |

## 派生链路

所有地方都遵循同一个模式：

```python
# 1. 指定 profile
profile = "project_mode_agent"

# 2. 从 profile JSON 派生 role_type
profile_data = ToolLoader._load_profile(profile)
role_type = profile_data.get("role_type", "Assistant")

# 3. role_type 只传给 Session（控制 overlay 行为）
session = project.session(session_id, role_type=role_type)

# 4. profile 传给 AgentLoop（控制工具加载）
agent = AgentLoop(..., profile=profile, ...)
```

没有任何地方直接硬编码 `role_type` 值。

## 工具加载流程

```
AgentLoop._register_default_tools()
    ↓
ToolLoader.load_for_profile(self.profile, context)
    ↓
读取 config/agent_profiles/{profile}.json → 获取 tools 列表
    ↓
从 config/tools.json 中筛选匹配的工具条目
    ↓
对每个工具，通过 inspect.signature 智能注入依赖
    ↓
注册到 ToolRegistry
```

## Profile 自动切换

AgentLoop 在项目切换时自动更新 profile：

```python
# switch_project()
if project_id == "Default":
    self.profile = "chat_mode_agent"
else:
    self.profile = "project_mode_agent"

# role_type 跟着重新派生
profile_data = ToolLoader._load_profile(self.profile)
self.role_type = profile_data.get("role_type", "Assistant")
```

`switch_mode()` 回退到 Default 时同理。

## SDD 的变化

旧代码中 SDD Worker 的工具是硬编码的：

```python
# 旧：手动实例化 + 从 parent 继承
sandboxed_tools = [
    ReadFileTool(session=worker_session),
    WriteFileTool(session=worker_session),
    # ... 8 个手动实例化的工具
]
# 再从 parent registry 继承其他工具
```

新代码统一走 profile：

```python
# 新：一行搞定
tools = loader.load_for_profile("sdd_worker", context)
```

Worker 和 Reviewer 各有独立 profile，工具集合清晰可控。

## role_type 的残留用途

`role_type` 没有被完全删除，它在以下地方仍然被消费（但都是从 profile 派生的）：

| 消费方 | 用途 |
|--------|------|
| `Session._role_type` | 控制文件 I/O 路由（overlay vs core） |
| `files.py` WriteFileTool/StrReplaceTool | 决定写入目标 |
| `context.py` 权限 prompt | 生成 `permissions_assistant.txt` 或 `permissions_worker.txt` |

这些都是 Session 层面的权限机制，与工具选择无关。

## 容错设计

- Profile 文件不存在 → `_load_profile()` 返回空 dict → `load_for_profile()` 回退到 `load_all()`
- Profile 中没有 `role_type` 字段 → 默认 `"Assistant"`
- Profile 中引用了 tools.json 里不存在的工具 → 静默跳过

## 工具访问控制

工具的可见性由三层机制控制，从粗到细：

| 层级 | 机制 | 说明 |
|------|------|------|
| 1. 全局开关 | `tools.json` 的 `enabled` 字段 | `enabled: false` 时，任何 profile 都无法加载该工具（全局禁用） |
| 2. Profile 选择 | profile JSON 的 `tools[]` 列表 | 只有列在 profile 中的工具才会被加载 |
| 3. 项目黑名单 | `project.config.tools_blacklist` | 已加载的工具在运行时被过滤，不出现在 API schema 中 |

旧架构中的 `project_restriction` 字段已移除。在 profile 系统下，工具的可用范围完全由 profile 声明决定，不再需要工具自身标记"我只能在项目中使用"。

典型场景：
- 想全局禁用某个实验性工具 → `enabled: false`
- 想让某类 agent 不使用某工具 → 不加到对应 profile 的 `tools[]`
- 想让某个项目禁用某工具 → 加到该项目的 `tools_blacklist`

## 如何扩展工具

添加新工具只需三步，不需要改任何框架代码：

### 第一步：写工具类

在 `agent/tools/` 下创建工具实现：

```python
# agent/tools/code_search.py
class CodeSearchTool:
    name = "code_search"
    description = "Search code in project files"

    def __init__(self, session=None):
        self.session = session

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"]
                }
            }
        }

    async def execute(self, query: str) -> str:
        # 实现搜索逻辑
        ...
```

### 第二步：注册到 tools.json

在 `config/tools.json` 中添加一条：

```json
{
    "name": "code_search",
    "class": "agent.tools.code_search.CodeSearchTool",
    "args": { "session": "{{session}}" },
    "enabled": true
}
```

`args` 中的 `{{session}}` 是模板变量，ToolLoader 会在实例化时自动替换为当前 Session 对象。

### 第三步：加到 profile

在需要这个工具的 profile JSON 的 `tools` 数组中加上工具名：

```json
// config/agent_profiles/project_mode_agent.json
{
  "tools": ["...", "code_search"]
}
```

哪个 agent 需要就加到哪个 profile，不需要的 profile 不加就行。

### 依赖注入机制

ToolLoader 通过 `inspect.signature` 检查工具构造函数的参数名，按以下优先级注入：

1. **显式声明**：`tools.json` 的 `args` 字段（支持 `{{placeholder}}` 模板语法）
2. **自动注入**：参数名与 context 字典的 key 匹配时自动注入（如 `session`、`provider`、`workspace`、`config`）
3. **跳过可选**：有默认值的参数不强制注入

也就是说，如果构造函数参数名恰好是 `session`、`provider`、`config` 等常见名称，连 `args` 都不用写 — ToolLoader 会自动处理。

可用的 context key 包括：`workspace`、`file_root`、`work_dir`、`provider`、`model`、`tools`、`tool_context`、`role_name`、`metadata_root`、`config`、`session`、`project`。

## 相关文件

- `config/agent_profiles/*.json` — 7 个 profile 定义
- `config/tools.json` — 工具注册表（profile 从这里筛选）
- `agent/tools/loader.py` — ToolLoader，负责 profile 加载和工具实例化
- `agent/loop.py` — AgentLoop，profile 的主要消费方
- `agent/scheduler/executor.py` — SDDExecutor，SDD worker/reviewer 的 profile 加载
- `agent/services/tool_context.py` — ToolContext，携带 profile 信息
