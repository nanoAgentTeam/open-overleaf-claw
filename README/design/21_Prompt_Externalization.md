# Prompt 管理体系（Phase-3 Prompt Externalization）

> 版本：Phase-3
> 日期：2026-02-23
> 前置：Design 15（LLM Engine）、Design 04（Context Management）
> 目标：建立 key-based prompt 组装机制，并将所有固定文案外部化到 `config/prompts/*.txt`

---

## 1. 背景与动机

### 1.1 组装问题：List append 导致重复膨胀

原始 `SystemPromptConfig` 使用 `base_prompt` + `extra_sections: List[str]` 结构。中间件通过 `append()` 追加指令，但 ReAct 循环中每次迭代都会重新执行中间件，导致：

- **重复膨胀** — 同一条警告被追加多次，system prompt 越来越长
- **无法更新** — 已追加的内容无法修改，只能继续追加
- **无法撤回** — 条件不再成立时，已注入的指令无法移除

### 1.2 文案问题：prompt 硬编码在 Python 代码中

项目已有 `config/prompts/` 模板体系（12 个 `.txt` 文件），但仅 `agent/context.py` 在使用。其余 13 个文件中的 30+ 条 prompt 全部硬编码：

- **调整文案必须改代码** — 即使只改一个措辞，也需要修改 `.py` 文件
- **prompt 散落各处** — 难以全局审查和统一管理 AI 行为指令

---

## 2. 整体架构

本次改动引入两个互补的机制，分别解决上述两个问题：

```
┌─────────────────────────────────────────────────────┐
│                config/prompts/*.txt                  │
│            （41 个模板文件，统一存放）                  │
└──────────────┬──────────────────────┬────────────────┘
               │                      │
    ┌──────────▼──────────┐  ┌───────▼────────────────┐
    │  core/prompts.py    │  │ config/registry.py     │
    │  render(name,       │  │ render_prompt(name,    │
    │    fallback, **kw)  │  │   **kw)                │
    │  零依赖 / 带fallback │  │ 依赖config层           │
    └──────────┬──────────┘  └───────┬────────────────┘
               │                      │
    ┌──────────▼──────────────────────▼────────────────┐
    │              PromptBuilder (key-based)            │
    │         core/llm/prompt_builder.py               │
    │  set(key, content) / remove(key) / build()       │
    └──────────────────────┬───────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────┐
    │          SystemPromptConfig (types.py)            │
    │     委托 PromptBuilder，兼容原有构造方式            │
    └──────────────────────┬───────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    Middleware        AgentEngine      ContextManager
    (set key-based   (build final     (assemble full
     warnings)        system msg)      system prompt)
```

数据流：
1. `core/prompts.render()` 从 `.txt` 模板加载文案并渲染变量
2. 中间件 / 引擎通过 `SystemPromptConfig.set(key, content)` 注入指令（幂等）
3. `ContextManager` 通过 `PromptBuilder` 按序拼接所有 section
4. `build()` 生成完整 system prompt，传给 LLM

---

## 3. PromptBuilder：key-based 组装

### 3.1 设计

`core/llm/prompt_builder.py`（~47 行），提供有序 KV section 注册表：

```python
class PromptBuilder:
    """Ordered KV section registry for system prompt assembly."""

    def set(self, key: str, content: str) -> PromptBuilder
    def remove(self, key: str) -> PromptBuilder
    def get(self, key: str) -> str | None
    def has(self, key: str) -> bool
    def keys(self) -> list[str]
    def build(self, separator: str = "\n\n") -> str
    def clear(self) -> None
```

| 特性 | 说明 |
|------|------|
| 幂等写入 | 同一 key 多次 `set()` 只保留最新值，不会重复 |
| 有序拼接 | 按首次插入顺序 `build()`，保证 prompt 结构稳定 |
| 可删除 | `remove()` 支持动态移除不再需要的 section |
| 零依赖 | 纯 Python，无外部依赖 |

### 3.2 SystemPromptConfig 委托

`SystemPromptConfig` 保留原有字段以兼容构造方式，内部委托给 `PromptBuilder`：

```python
@dataclass
class SystemPromptConfig:
    base_prompt: str = "You are a helpful assistant."
    extra_sections: List[str] = field(default_factory=list)

    def __post_init__(self):
        self._pb = PromptBuilder()
        self._pb.set("base", self.base_prompt)
        for i, section in enumerate(self.extra_sections):
            self._pb.set(f"_extra_{i}", section)

    def set(self, key: str, content: str) -> SystemPromptConfig:
        self._pb.set(key, content)
        return self

    def build(self) -> str:
        return self._pb.build()
```

所有现有代码无需修改 — `SystemPromptConfig(base_prompt="...")` 构造方式不变，同时支持 `config.set("mw:budget", "...")` 的 key-based 写入。

### 3.3 使用场景

**中间件注入**（跨迭代幂等，解决重复膨胀问题）：

```python
# 每次迭代 set 同一个 key，只保留最新值
session.system_config.set("mw:loop_breaker", rendered_warning)
session.system_config.set("mw:drift_reminder", rendered_reminder)
session.system_config.set("mw:budget_warning", rendered_budget)
```

**ContextManager 组装**（按序拼接完整 system prompt）：

```python
pb = self.prompt_builder
pb.set("base", self.system_prompt)
pb.set("identity", identity)
pb.set("project_guidance", project_guidance)
pb.set("workspace", workspace_info)
pb.set("permissions", permissions)
pb.set("memory_protocol", memory_protocol)
pb.set("consolidated_memory", memory)
pb.set("active_context", context)
pb.set("task_phase", task_phase)
return pb.build()  # 按顺序拼接，\n\n 分隔
```

key 命名约定：`{来源}:{功能}`，如 `mw:loop_breaker`、`skill:arxiv-search`、`env_context`。

### 3.4 文件结构

```
core/llm/prompt_builder.py    ← 核心实现
agent/prompt_builder.py        ← re-export shim（from core.llm.prompt_builder import PromptBuilder）
core/llm/types.py              ← SystemPromptConfig 委托给 PromptBuilder
```

---

## 4. 模板加载器：`core/prompts.py`

`core/llm/` 层无法访问 `ConfigRegistry`（属于 agent 层），因此新建零依赖的轻量 loader：

```python
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"

@lru_cache(maxsize=64)
def _load_raw(name: str) -> Optional[str]:
    path = _PROMPTS_DIR / name
    return path.read_text("utf-8") if path.exists() else None

def render(template_name: str, fallback: str, **kwargs) -> str:
    raw = _load_raw(template_name) or fallback
    try:
        return raw.format(**kwargs)
    except KeyError:
        return raw
```

| 特性 | 说明 |
|------|------|
| 零依赖 | 不依赖 agent/config 层，`core/` 和 `agent/` 均可使用 |
| lru_cache | 同一模板只读一次磁盘 |
| fallback | 文件不存在时回退到硬编码字符串，保证向后兼容 |
| KeyError 容错 | 模板变量缺失时返回原始模板文本，不崩溃 |

与现有 `ConfigRegistry.render_prompt()` 的关系：两套 loader 共享同一个 `config/prompts/` 目录，互不冲突。`ConfigRegistry` 继续服务 `agent/context.py` 的模板渲染，`core/prompts` 服务其余所有层。

---

## 5. 模板文件清单

共新增 20 个 `.txt` 模板文件，按层级分为四组：

### 5.1 Middleware（3 个）

| 文件 | 变量 | 用途 |
|------|------|------|
| `mw_loop_breaker.txt` | `{tool_name}`, `{max_repeats}` | 循环检测警告 |
| `mw_drift_reminder.txt` | `{iteration}`, `{original_prompt_preview}` | 语义漂移提醒 |
| `mw_budget_warning.txt` | — | 执行预算超限 |

### 5.2 Engine（2 个）

| 文件 | 变量 | 用途 |
|------|------|------|
| `engine_iteration_info.txt` | `{iteration}`, `{max_iterations}` | 迭代计数 |
| `engine_iteration_urgent.txt` | `{iteration}`, `{max_iterations}` | 接近上限警告 |

### 5.3 Scheduler（3 个）

| 文件 | 变量 | 用途 |
|------|------|------|
| `scheduler_planner.txt` | — | DAG 规划器系统 prompt |
| `scheduler_worker_base.txt` | `{agent}`, `{description}` | Worker 基础 prompt |
| `scheduler_reviewer.txt` | — | Reviewer 系统 prompt |

### 5.4 Agent / Tool（12 个）

| 文件 | 变量 | 用途 |
|------|------|------|
| `swarm_task_isolation.txt` | `{project_id}` | 任务子代理隔离指令 |
| `git_agent.txt` | — | Git 管理助手系统 prompt |
| `browser_force_json.txt` | — | 浏览器 JSON 格式强制 |
| `task_phase_understand.txt` | `{goal_line}`, `{round_line}` | Task Mode 理解阶段 |
| `task_phase_propose.txt` | `{goal_line}`, `{round_line}` | Task Mode 提案阶段 |
| `task_phase_plan.txt` | `{goal_line}`, `{round_line}` | Task Mode 计划阶段 |
| `task_phase_execute.txt` | `{goal_line}`, `{round_line}` | Task Mode 执行阶段 |
| `task_phase_finalize.txt` | `{goal_line}`, `{round_line}` | Task Mode 整合阶段 |
| `task_phase_post_commit.txt` | `{goal_line}`, `{round_line}` | Task Mode 提交后阶段 |
| `loop_meta_diagnosis.txt` | `{role_name}`, `{recent_actions}` | 死循环元诊断 |
| `loop_commit_summary.txt` | `{file_list}` | 自动提交摘要 |
| `loop_research_topic.txt` | `{combined_text}` | 研究主题提取 |

---

## 6. 迁移模式

每处改动遵循统一模式：

```python
# Before — 硬编码 f-string
session.system_config.set(
    "mw:loop_breaker",
    f"WARNING: You have attempted to call '{name}' ..."
)

# After — 模板 + fallback
from core.prompts import render as render_prompt

_LOOP_BREAKER_FALLBACK = (
    "WARNING: You have attempted to call '{tool_name}' with the same arguments "
    "{max_repeats} times consecutively. ..."
)
session.system_config.set(
    "mw:loop_breaker",
    render_prompt("mw_loop_breaker.txt", _LOOP_BREAKER_FALLBACK,
                  tool_name=name, max_repeats=self.max_repeats)
)
```

关键原则：
- **fallback 与模板内容保持一致** — 删除模板文件后行为不变
- **分隔符放在调用处** — 模板内容不含前导 `\n\n`，由调用方控制拼接
- **条件拼接逻辑保留在代码中** — 动态段落（依赖注入、proposal 上下文等）不抽模板

### 有意未迁移的 prompt

以下 prompt 因为是动态数据格式化或条件拼接，按设计保留在代码中：

- `executor.py` 的条件 `+=` 段落（依赖注入警告、proposal、session context、review feedback）
- `engine.py` 的 skill selector query（动态查询构造）
- `engine.py` 的 citation block（动态数据格式化）
- `executor.py` 的 reviewer user message（多变量动态拼接）

---

## 7. 改动文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `core/llm/prompt_builder.py` | 新建 | PromptBuilder 核心实现，~47 行 |
| `agent/prompt_builder.py` | 新建 | re-export shim |
| `core/llm/types.py` | 重构 | SystemPromptConfig 委托 PromptBuilder |
| `core/prompts.py` | 新建 | 模板 loader，~28 行 |
| `core/llm/middleware.py` | 3 处 | 循环检测 / 漂移提醒 / 预算警告 |
| `core/llm/engine.py` | 2 处 | 迭代信息 |
| `agent/scheduler/planner.py` | 1 处 | Planner 系统 prompt |
| `agent/scheduler/executor.py` | 2 处 | Worker base + Reviewer |
| `agent/git_agent.py` | 1 处 | SYSTEM_PROMPT 常量 |
| `agent/tools/browser.py` | 1 处 | JSON 格式强制 |
| `agent/context.py` | 6 处 | 6 个 Task Phase prompt |
| `agent/loop.py` | 3 处 | 元诊断 / 提交摘要 / 研究主题 |

共 3 个新 Python 文件 + 9 个修改 + 20 个模板文件。

---

## 8. 开发规范

### 8.1 模板命名约定

所有模板文件统一使用 `{组件前缀}_{功能}.txt` 格式：

| 前缀 | 适用层 | 示例 |
|------|--------|------|
| `ctx_` | Context 组装（身份/记忆/摘要） | `ctx_identity.txt` |
| `mw_` | 中间件 | `mw_loop_breaker.txt` |
| `engine_` | LLM 引擎 | `engine_iteration_info.txt` |
| `scheduler_` | 调度器 | `scheduler_worker_base.txt` |
| `task_phase_` | Task Mode 阶段 | `task_phase_execute.txt` |
| `loop_` | AgentLoop | `loop_meta_diagnosis.txt` |
| `mode_` | 模式引导 | `mode_chat.txt` |
| `project_` | 项目引导 | `project_active.txt` |
| `permissions_` | 权限声明 | `permissions_assistant.txt` |
| `agent_` | 独立 agent 系统 prompt | `agent_git.txt` |
| `tool_` | 工具专用 prompt | `tool_browser_force_json.txt` |

### 8.2 变量占位符

- 使用 Python `str.format()` 语法：`{variable_name}`
- JSON 花括号必须转义：`{{` / `}}`
- 变量名使用 snake_case

### 8.3 新增模板流程

1. 在 `config/prompts/` 创建 `.txt` 文件
2. 在代码中定义 `_FALLBACK` 常量（内容与模板一致）
3. 调用 `render_prompt("xxx.txt", _FALLBACK, key=value)`
4. 分隔符（`\n\n`）放在调用处，不放在模板中

### 8.4 PromptBuilder key 命名

格式：`{来源}:{功能}`

| 来源 | 示例 key | 写入方 |
|------|----------|--------|
| `mw` | `mw:loop_breaker` | 中间件 |
| `skill` | `skill:arxiv-search` | 技能注入 |
| 无前缀 | `base`, `identity`, `workspace` | ContextManager |
