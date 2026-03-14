# 项目记忆存储统一化重构（Phase-2 Memory）

> 版本：Phase-2 Memory Blueprint
> 日期：2026-02-22
> 前置：Design 19（研究雷达自动化 Phase-1）
> 目标：统一定时任务/autoplan 链路的记忆存储，消除冗余，为全局统一预留接口

---

## 1. 现状问题诊断

### 1.1 runs/ 与 entries/ 双写

`AutomationRuntime._run_and_log()` 每次执行后做两件事：
1. `store.add_run(run)` → 写入 `automation/runs/*.json`（结构化运行日志）
2. `ks.add_entry(...)` → 写入 `knowledge/entries/MEM-*.md`（自然语言运行摘要）

再加上 `job_states/<job_id>.json` 存了一份 last_run 快照。**同一次运行的信息散落三处**，且 runs/ 中的结构化日志在后续链路中几乎只被 `prompt_context` 的 `_recent_runs()` 读取，利用率低。

### 1.2 MEMORY.md 孤岛

`agent/tools/memory.py` 的 `SaveMemoryTool` 写入 `<metadata_root>/memory/memory/MEMORY.md`，`RetrieveMemoryTool` 用关键词 grep 检索。这套数据与 `ProjectKnowledgeStore` 的 entries/index **互不可见**：
- memory_nav/memory_list 查不到 MEMORY.md 的内容
- memory_search 也搜不到

### 1.3 prompt_context 与 render_system_memory_brief 逻辑重复

| 方法 | 位置 | 消费者 |
|------|------|--------|
| `AutomationPromptContextBuilder.render()` | `core/automation/prompt_context.py` | 定时任务执行 |
| `ProjectKnowledgeStore.render_system_memory_brief()` | `core/profile/fs_memory.py` | agent chat system prompt / memory_brief tool |

两者都拼接 profile + trajectory + compact_index，前者多了 job_state + recent_runs + 执行约束。各自维护，容易不一致。

### 1.4 Profile 构建硬编码

`_build_research_core_profile` 只认 `.tex` 文件，`_build_user_preference_profile` 用硬编码关键词匹配。换项目类型或加新画像需改 `fs_memory.py` 源码。

### 1.5 scope 隐式约定

scope 格式（`project`、`job:radar.daily.scan`、`user`）全靠 prompt 自然语言约定和 `_scope_domain()` 的冒号分割，无枚举、无校验。

---

## 2. 设计目标

1. **一个 Store，统一入口**：定时任务的运行记录、Agent 写入的笔记、用户保存的事实，全部进入同一套 entries + index。
2. **消除主链路双写**：删除 `automation/runs/` 目录，运行记录统一为 `kind=job_run` 的 entry（兼容镜像双写除外）。
3. **统一上下文渲染**：一处维护 brief 拼接逻辑，多处消费。
4. **Profile 可插拔**：构建器协议化，支持注册新类型。
5. **本次只改定时任务/autoplan 链路**：agent chat 的 memory 逻辑（`context.py` 中的 `render_system_memory_brief` 调用、memory_brief tool）保持不变。
6. **兼容分轨（不双读）**：Phase-2 中 agent chat 继续读取旧路径 `.project_memory/knowledge/`，自动化/autoplan 读取新路径 `.project_memory/`；不做新旧双读。

---

## 3. 设计原则

延续 Design 19 的核心原则，新增：

1. **单一数据源（Single Source of Truth）**：同一份运行信息只落盘一次，其他位置只存指针。
2. **kind + scope 组合替代目录分离**：不再用物理目录区分数据类型，用元数据字段区分。
3. **渐进披露不变**：system prompt 只注入 brief + ID 索引，全文按需 `memory_get`。
4. **最小侵入**：本次重构不改 agent chat 链路，不改 tool 注册机制（`config/tools.json`），不改 `AgentLoop`。
5. **兼容策略以分轨为先**：不引入双读逻辑；若确有跨链路可见性需求，可在极小范围内启用可配置双写（mirror）。

---

## 4. 目标架构

### 4.1 目录结构（重构后）

```text
.project_memory/
├── entries/                          ← 统一条目存储（所有记忆）
│   ├── MEM-0001.md                   ← kind=note, scope=project
│   ├── MEM-0002.md                   ← kind=job_run, scope=job:radar.daily.scan
│   └── ...
├── index.json                        ← 全量元数据索引
├── index_compact.md                  ← 紧凑索引（prompt 注入用）
│
├── profiles/                         ← Profile 画像（保留）
│   ├── research_core.current.json
│   ├── research_core.history.jsonl
│   ├── user_preference.current.json
│   └── user_preference.history.jsonl
│
├── jobs/                             ← 作业定义（从 automation/jobs/ 提上来）
│   └── radar.daily.scan.json
│
└── job_states/                       ← 作业状态（精简为指针）
    └── radar.daily.scan.json
```

**删除的目录/文件：**
- `automation/runs/` — 运行记录统一进 entries
- `automation/jobs/` — 提升到 `.project_memory/jobs/`
- `automation/job_states/` — 提升到 `.project_memory/job_states/`
- `automation/subscriptions.json` — 并入 job 定义的 `output_policy` 或提升到 `.project_memory/subscriptions.json`
- `knowledge/` 中间层目录 — entries/profiles/index 直接放在 `.project_memory/` 下

### 4.2 模块依赖变化

```text
重构前:
  AutomationRuntime ──→ FSAutomationStore (jobs + runs + states + subscriptions)
                    ──→ ProjectKnowledgeStore (entries + profiles + index)
  AutomationExecutor ──→ AutomationPromptContextBuilder
                           ├─→ FSAutomationStore.list_runs / get_job_state
                           └─→ ProjectKnowledgeStore.read_profile / read_compact_index
  RadarAutoplanService ──→ FSAutomationStore + ProjectKnowledgeStore

重构后:
  AutomationRuntime ──→ ProjectMemoryStore (entries + profiles + index + jobs + states)
  AutomationExecutor ──→ ContextRenderer
                           └─→ ProjectMemoryStore
  RadarAutoplanService ──→ ProjectMemoryStore
```

---

## 5. 统一 Entry Schema

### 5.1 索引记录（index.json 中每条）

```json
{
  "id": "MEM-0042",
  "kind": "job_run",
  "scope": "job:radar.daily.scan",
  "intent": "job_progress",
  "title": "radar.daily.scan run @ 2026-02-22T09:10",
  "summary": "扫描到 3 篇相关论文，1 篇高相关...",
  "tags": ["automation", "job:radar.daily.scan", "status:success"],
  "source": "automation_runtime",
  "created_at": "2026-02-22T09:10:25",
  "updated_at": "2026-02-22T09:10:25",
  "ttl": "30d",
  "parent_id": null,
  "path": "entries/MEM-0042.md"
}
```

### 5.2 新增字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `kind` | string | 条目类型：`note` / `fact` / `job_run` / `insight` / `decision` |
| `ttl` | string \| null | 过期策略：`"7d"` / `"30d"` / `null`（永久）。`job_run` 建议 `"30d"`，`note`/`insight` 建议 `null` |
| `parent_id` | string \| null | 关联父条目 ID。周报可引用日报的 MEM-ID，形成记忆链 |
| `created_at` | string | 创建时间（新增，与 `updated_at` 分离） |

### 5.3 kind 枚举（推荐值，不做强校验）

| kind | 典型 scope | 典型 source | 说明 |
|------|-----------|-------------|------|
| `note` | `project` | `agent` | Agent 主动记录的项目笔记 |
| `fact` | `user` | `user` / `agent` | 用户要求记住的事实（替代 MEMORY.md） |
| `job_run` | `job:<job_id>` | `automation_runtime` | 定时任务运行摘要 |
| `insight` | `project` | `agent` | 分析洞察 |
| `decision` | `project` / `job:*` | `agent` | 决策记录 |

说明：`kind`/`scope`/`ttl` 在 Phase-2 保持自由文本策略，不做强校验，不拦截未知值；调用方自约定并通过 tags 兜底检索。

### 5.4 scope 规范

格式：`<domain>` 或 `<domain>:<qualifier>`

| domain | 示例 | 说明 |
|--------|------|------|
| `project` | `project` | 项目级通用 |
| `job` | `job:radar.daily.scan` | 绑定到特定作业 |
| `user` | `user` | 用户级偏好/事实 |
| `chat` | `chat:<chat_id>` | 绑定到特定会话（未来） |

`_scope_domain()` 逻辑不变：冒号前为 domain，无冒号则整体为 domain。

---

## 6. 统一 Store API：ProjectMemoryStore

### 6.1 类定义

新建 `core/memory/store.py`，替代 `core/profile/fs_memory.py` 中与定时任务相关的职责。

```python
class ProjectMemoryStore:
    """统一的项目记忆存储。

    合并原 ProjectKnowledgeStore 的 entries/index/profiles 能力
    与原 FSAutomationStore 的 runs 写入能力。
    """

    def __init__(self, project: Any):
        self.project = project
        self.base_dir = project.root / ".project_memory"
        self.entries_dir = self.base_dir / "entries"
        self.profiles_dir = self.base_dir / "profiles"
        self.index_json = self.base_dir / "index.json"
        self.index_compact = self.base_dir / "index_compact.md"
```

### 6.2 核心 API

```python
# ── 条目 CRUD ──
def add(self, *, kind, scope, intent, title, content, tags, source, ttl, parent_id) -> str: ...
def get(self, memory_id: str) -> dict | None: ...
def update(self, memory_id: str, patch: dict) -> bool: ...      # 未来扩展
def delete(self, memory_id: str) -> bool: ...                    # 未来扩展

# ── 三级导航（保留现有模式，增加 kind 过滤）──
def nav(self, domain="all", intent="", kind="", limit=30) -> list[dict]: ...
def list_by_scope(self, scope, *, intent="", kind="", since="", limit=20, cursor="") -> dict: ...
def search(self, query, *, kind="", scope="", top_k=5) -> list[dict]: ...

# ── 索引 ──
def compact_index(self, limit=30, kind_filter="") -> str: ...
def refresh_compact_index(self, limit=30) -> str: ...

# ── Profile ──
def read_profile(self, name: str) -> dict: ...
def write_profile(self, name: str, payload: dict): ...
def append_profile_history(self, name: str, payload: dict): ...
def read_profile_history(self, name: str, limit=20) -> list[dict]: ...
def summarize_research_trajectory(self, limit=6) -> str: ...
def refresh_profiles(self, builders: list | None = None): ...

# ── 生命周期 ──
def gc(self, now: datetime | None = None, *, protect_job_state_refs: bool = True) -> int:
    """清理过期条目（基于 ttl）。默认保护 job_state.last_entry_id 指向的条目。返回清理数量。"""
```

### 6.3 与现有 ProjectKnowledgeStore 的关系

**本次实施策略：继承 + 扩展**，而非重写。

```python
# core/memory/store.py
from core.profile.fs_memory import ProjectKnowledgeStore

class ProjectMemoryStore(ProjectKnowledgeStore):
    """在 ProjectKnowledgeStore 基础上：
    1. 重写 base_dir 指向 .project_memory/（去掉 knowledge/ 中间层）
    2. 新增 kind 过滤参数
    3. 新增 ttl / parent_id / created_at 字段支持
    4. 新增 gc() 方法
    5. 新增 refresh_profiles(builders) 可插拔构建
    """
```

**为什么继承而非重写：**
- `ProjectKnowledgeStore` 的 entries/index/profiles 逻辑已经稳定
- agent chat 链路仍然通过 `ProjectKnowledgeStore` 访问（本次不改）
- 继承可以复用所有现有方法，只 override 需要变化的部分
- 未来全局统一时，再将 `ProjectKnowledgeStore` 的调用方迁移到 `ProjectMemoryStore`

### 6.4 并发与 ID 分配策略

为避免并发写入时的 `MEM-xxxx` 冲突，`ProjectMemoryStore.add()` 采用“文件锁 + 临界区内分配 ID + 原子写入”：

```python
# core/memory/store.py
def add(...)-> str:
    with self._file_lock("index.lock"):
        records = self._load_index()
        mem_id = self._next_memory_id_from_records(records)   # 在锁内分配
        self._atomic_write_entry(mem_id, content)
        self._append_index_record(records, ...)
        self._save_index(records)
    self.refresh_compact_index()
    return mem_id
```

锁实现建议：
- 进程内：`threading.Lock`（按 project_id 维度）
- 跨进程：`fcntl.flock(index.lock)`（Unix）
- 锁获取失败：快速失败并重试（指数退避，最多 3 次）

---

## 7. ContextRenderer：统一上下文渲染

### 7.1 设计

新建 `core/memory/context_renderer.py`，替代 `AutomationPromptContextBuilder` 和 `render_system_memory_brief` 中的重复逻辑。

```python
class ContextRenderer:
    """统一的记忆上下文渲染器。一处维护，多处消费。"""

    def __init__(self, store: ProjectMemoryStore):
        self.store = store

    def render_base_brief(self, index_limit=12) -> str:
        """基础 brief：profile snapshots + trajectory + compact_index。
        供 agent chat system prompt 和定时任务共用。
        """
        ...

    def render_job_context(
        self,
        job: AutomationJob,
        job_state: dict,
        recent_entries: list[dict],
    ) -> str:
        """定时任务上下文 = base_brief + job_state + 近期运行条目 + 执行约束。"""
        brief = self.render_base_brief(index_limit=10)
        # 追加 job 特有上下文
        ...

    def render_autoplan_context(
        self,
        jobs: list[dict],
        states: dict[str, dict],
        recent_entries: list[dict],
    ) -> str:
        """autoplan 上下文 = base_brief + 全部 jobs + states + 近期运行。"""
        ...
```

### 7.2 消费者映射

| 消费者 | 现在调用 | 重构后调用 |
|--------|---------|-----------|
| 定时任务执行 (`executor.py`) | `AutomationPromptContextBuilder.render()` | `ContextRenderer.render_job_context()` |
| autoplan (`autoplan.py`) | 手动拼接 profiles + compact_index + trajectory | `ContextRenderer.render_autoplan_context()` |
| agent chat system prompt (`context.py`) | `ProjectKnowledgeStore.render_system_memory_brief()` | **本次不改**，保持原样 |
| memory_brief tool (`memory_tools.py`) | `ProjectKnowledgeStore.render_system_memory_brief()` | **本次不改**，保持原样 |

### 7.3 render_job_context 输出结构

```text
[AUTOMATION CONTEXT]
你正在执行任务: radar.daily.scan (Radar Daily Scan)

执行约束:
- 只有在确实需要通知时才调用 notify_push
- 记忆检索主路径：memory_nav -> memory_list -> memory_get
- memory_search 仅作为兜底
- 任务相关记忆建议 scope 使用 job:radar.daily.scan

项目研究快照:
- topic: radar / detection
- stage: writing
- keywords: radar, detection, ...

用户偏好快照:
- push_style: important_only
- language: zh

研究方向近期轨迹:
- 2026-02-20T14:00: topic=...; stage=...; keywords=...

该任务近期状态:
- last_run_at: 2026-02-22T09:10:25
- last_status: success
- last_entry_id: MEM-0042

该任务近期运行记录:
- [MEM-0042] radar.daily.scan run @ 2026-02-22T09:10 | 扫描到 3 篇相关论文...
- [MEM-0038] radar.daily.scan run @ 2026-02-21T09:10 | 无新发现...

记忆索引（可用 memory_get 按 ID 拉取全文）:
- [MEM-0042] radar.daily.scan run @ 2026-02-22T09:10: ...
- [MEM-0041] Project Assessment: ...
```

关键变化：近期运行记录不再从 `runs/*.json` 读取，而是从 entries 中按 `kind=job_run, scope=job:<job_id>` 过滤。

---

## 8. 可插拔 Profile Builder

### 8.1 协议定义

```python
# core/memory/profile_builder.py
from typing import Any, Protocol

class ProfileBuilder(Protocol):
    """Profile 构建器协议。"""
    name: str

    def build(self, project: Any) -> dict[str, Any]: ...
```

### 8.2 内置实现

将现有 `_build_research_core_profile` 和 `_build_user_preference_profile` 抽为独立类：

```python
# core/memory/builders/tex_research.py
class TexResearchProfileBuilder:
    name = "research_core"

    def build(self, project):
        # 原 _build_research_core_profile 逻辑搬迁
        ...

# core/memory/builders/chat_preference.py
class ChatPreferenceProfileBuilder:
    name = "user_preference"

    def build(self, project):
        # 原 _build_user_preference_profile 逻辑搬迁
        ...
```

### 8.3 注册与调用

```python
# ProjectMemoryStore
DEFAULT_BUILDERS = [TexResearchProfileBuilder(), ChatPreferenceProfileBuilder()]

def refresh_profiles(self, builders: list[ProfileBuilder] | None = None) -> dict[str, Any]:
    builders = builders or DEFAULT_BUILDERS
    results = {}
    for builder in builders:
        try:
            payload = builder.build(self.project)
            self.write_profile(builder.name, payload)
            self.append_profile_history(builder.name, payload)
            results[builder.name] = payload
        except Exception as e:
            logger.warning(f"Profile builder {builder.name} failed: {e}")
    return results
```

### 8.4 扩展示例（未来）

```python
# 用户自定义 builder，无需改 fs_memory.py
class CodeQualityProfileBuilder:
    name = "code_quality"

    def build(self, project):
        py_files = list(project.core.glob("**/*.py"))
        # 统计 lint 问题、测试覆盖率等
        return {"files": len(py_files), "quality_score": ...}
```

---

## 9. Job 状态精简

### 9.1 现状

`job_states/<job_id>.json` 当前存储：

```json
{
  "last_run_at": "...",
  "last_status": "success",
  "last_run_id": "run_abc123",
  "last_trigger": "schedule",
  "last_error": "...(最多500字)",
  "last_note_ref": "MEM-0042"
}
```

`last_run_id` 指向 `runs/*.json` 中的文件，`last_note_ref` 指向 `entries/MEM-*.md`。两个指针指向两份数据。

### 9.2 重构后

```json
{
  "job_id": "radar.daily.scan",
  "last_run_at": "2026-02-22T09:10:25",
  "last_status": "success",
  "last_entry_id": "MEM-0042",
  "run_count": 15,
  "consecutive_failures": 0,
  "updated_at": "2026-02-22T09:10:25"
}
```

变化：
- 删除 `last_run_id`（不再有 runs/ 文件）
- `last_note_ref` 重命名为 `last_entry_id`（语义更清晰）
- 删除 `last_error`（详情在 entry 正文中）
- 删除 `last_trigger`（详情在 entry 正文中）
- 新增 `run_count`（累计运行次数，便于统计）
- 新增 `consecutive_failures`（连续失败次数，便于告警判断）

---

## 10. Tool 层变化

### 10.1 本次实施范围内的变化

| Tool | 变化 | 说明 |
|------|------|------|
| `memory_nav` | 新增 `kind` 参数 | 支持按 kind 过滤 scope 聚合 |
| `memory_list` | 新增 `kind` 参数 | 支持按 kind 过滤条目列表 |
| `memory_write` | 新增 `ttl`、`parent_id` 参数 | 支持过期策略和关联 |
| 其余 tools | 不变 | `memory_get`、`memory_search`、`memory_brief`、`profile_read`、`profile_refresh` |

### 10.2 未来计划（全局统一时）

| Tool | 变化 | 说明 |
|------|------|------|
| `save_memory` | 删除 | 由 `memory_write(kind="fact", scope="user")` 替代 |
| `retrieve_memory` | 删除 | 由 `memory_search` 替代 |
| `profile_refresh` | 降级为内部方法 | 不再暴露给 LLM，由 runtime 自动调用 |

---

## 11. 迁移路径（分步实施）

### Step 1：新建 ProjectMemoryStore（继承 ProjectKnowledgeStore）

- 新建 `core/memory/__init__.py`、`core/memory/store.py`
- `ProjectMemoryStore` 继承 `ProjectKnowledgeStore`
- 重写 `base_dir` 指向 `.project_memory/`（去掉 `knowledge/` 中间层）
- 新增 `ttl`、`parent_id`、`created_at` 字段支持
- 新增 `kind` 过滤参数到 `nav()`、`list_by_scope()`、`search()`
- 新增 `gc()` 方法
- 不做新旧双读，不做自动软迁移（symlink/复制）；旧路径留给 agent chat，自动化链路直接写新路径
- 新增 `index.lock` 并将 ID 分配与 index 写入放入同一临界区

涉及文件：
- 新建 `core/memory/__init__.py`
- 新建 `core/memory/store.py`

### Step 2：抽取 ProfileBuilder

- 新建 `core/memory/profile_builder.py`（协议定义）
- 新建 `core/memory/builders/__init__.py`
- 新建 `core/memory/builders/tex_research.py`（从 `fs_memory.py._build_research_core_profile` 搬迁）
- 新建 `core/memory/builders/chat_preference.py`（从 `fs_memory.py._build_user_preference_profile` 搬迁）
- `ProjectMemoryStore.refresh_profiles()` 接受 builders 列表

涉及文件：
- 新建 `core/memory/profile_builder.py`
- 新建 `core/memory/builders/tex_research.py`
- 新建 `core/memory/builders/chat_preference.py`

### Step 3：新建 ContextRenderer

- 新建 `core/memory/context_renderer.py`
- 实现 `render_base_brief()`、`render_job_context()`、`render_autoplan_context()`
- `render_base_brief()` 逻辑从 `ProjectKnowledgeStore.render_system_memory_brief()` 提取

涉及文件：
- 新建 `core/memory/context_renderer.py`

### Step 4：改造 AutomationRuntime

- `_run_and_log()` 中：
  - 删除 `store.add_run(run)` 调用
  - 改为 `memory_store.add(kind="job_run", scope=f"job:{job.id}", ttl="30d", ...)`
  - `job_state` 精简为新 schema（`last_entry_id`、`run_count`、`consecutive_failures`）
  - 可选：在 `mirror_legacy_memory=true` 时，额外双写一条旧 `ProjectKnowledgeStore.add_entry(...)`（仅兼容观测，不作为主数据源）
- `bootstrap_project()` 中：
  - `ProjectKnowledgeStore` → `ProjectMemoryStore`
  - `ks.refresh_default_profiles()` → `memory_store.refresh_profiles()`

涉及文件：
- 修改 `core/automation/runtime.py`

### Step 5：改造 AutomationExecutor

- `execute_job()` 中：
  - `AutomationPromptContextBuilder` → `ContextRenderer`
  - 近期运行记录从 entries 按 `kind=job_run` 过滤获取

涉及文件：
- 修改 `core/automation/executor.py`
- 删除或标记废弃 `core/automation/prompt_context.py`

### Step 6：改造 RadarAutoplanService

- `reconcile_project()` 中：
  - `FSAutomationStore` + `ProjectKnowledgeStore` → `ProjectMemoryStore`
  - `store.list_runs()` → `memory_store.list_by_scope(scope=..., kind="job_run")`
  - 上下文拼接改用 `ContextRenderer.render_autoplan_context()`

涉及文件：
- 修改 `agent/radar_autopilot/autoplan.py`

### Step 7：FSAutomationStore 瘦身

- 删除 `add_run()`、`list_runs()` 方法（运行记录已统一到 entries）
- 保留 `list_jobs()`、`get_job()`、`upsert_job()`、`disable_job()`、`delete_job()`（作业管理）
- 保留 `get_job_state()`、`update_job_state()`（状态管理）
- 保留 `get_subscriptions()`、`add_subscription()`、`remove_subscription()`（订阅管理）
- 更新 `base_dir` 路径：`jobs/`、`job_states/` 提升到 `.project_memory/` 下

涉及文件：
- 修改 `core/automation/store_fs.py`

### Step 8：memory_tools 增加 kind 过滤

- `MemoryNavTool.parameters_schema` 新增 `kind` 参数
- `MemoryListTool.parameters_schema` 新增 `kind` 参数
- `MemoryWriteTool.parameters_schema` 新增 `ttl`、`parent_id` 参数
- 内部 `_store()` 方法返回 `ProjectMemoryStore`（如果有 project context）

涉及文件：
- 修改 `agent/tools/memory_tools.py`

### Step 9：更新 radar_defaults prompt

- 各默认雷达任务的 prompt 中，更新记忆使用说明：
  - 提及 `kind` 过滤能力
  - 提及 `ttl` 建议

涉及文件：
- 修改 `core/automation/radar_defaults.py`

---

## 12. 本次实施范围

### 12.1 改（本次做）

| 模块 | 变化 |
|------|------|
| `core/memory/store.py` | 新建，继承 ProjectKnowledgeStore |
| `core/memory/profile_builder.py` | 新建，ProfileBuilder 协议 |
| `core/memory/builders/*.py` | 新建，两个内置 builder |
| `core/memory/context_renderer.py` | 新建，统一渲染器 |
| `core/automation/runtime.py` | 改用 ProjectMemoryStore + ContextRenderer |
| `core/automation/executor.py` | 改用 ContextRenderer |
| `core/automation/store_fs.py` | 删除 runs 相关方法，更新路径 |
| `agent/radar_autopilot/autoplan.py` | 改用 ProjectMemoryStore |
| `agent/tools/memory_tools.py` | 新增 kind/ttl/parent_id 参数 |
| `core/automation/radar_defaults.py` | 更新 prompt 中的记忆使用说明 |

### 12.2 不改（本次不动）

| 模块 | 原因 |
|------|------|
| `agent/context.py` | agent chat system prompt 注入逻辑不变 |
| `agent/tools/memory.py` | SaveMemoryTool/RetrieveMemoryTool 暂不删除 |
| `core/profile/fs_memory.py` | 保留，作为 ProjectMemoryStore 的父类 |
| `config/tools.json` | tool 注册配置不变 |
| `agent/loop.py` | AgentLoop 不变 |

---

## 13. 未来计划（全局统一 Phase-3）

### 13.1 agent chat 记忆统一

- `agent/context.py` 中的 `render_system_memory_brief()` 调用迁移到 `ContextRenderer.render_base_brief()`
- `memory_brief` tool 内部改用 `ContextRenderer`
- 删除 `ProjectKnowledgeStore.render_system_memory_brief()` 方法

### 13.2 MEMORY.md 退役

- `SaveMemoryTool` 改为代理到 `ProjectMemoryStore.add(kind="fact", scope="user")`
- `RetrieveMemoryTool` 改为代理到 `ProjectMemoryStore.search(kind="fact")`
- 最终删除 `agent/tools/memory.py`

### 13.3 ProjectKnowledgeStore 退役

- 所有调用方迁移到 `ProjectMemoryStore`
- `core/profile/fs_memory.py` 标记为 deprecated，最终删除
- `core/profile/__init__.py` 改为导出 `ProjectMemoryStore`

### 13.4 存储后端可替换

- `ProjectMemoryStore` 抽象为接口
- 提供 `FSProjectMemoryStore`（当前实现）和 `SQLiteProjectMemoryStore`（未来）
- 通过项目配置选择后端

### 13.5 向量检索

- 当 entries 数量超过阈值（如 500 条），`search()` 可选启用轻量 embedding
- 候选方案：sqlite-vss 或本地 sentence-transformers

---

## 14. 验收测试方案

### 14.1 功能验收

1. **运行记录统一存储**
   - 前置：执行一个定时任务。
   - 断言：`entries/` 下新增 `MEM-*` 文件，`kind=job_run`；`automation/runs/` 不再有新文件。

2. **kind 过滤**
   - 前置：写入 `kind=note` 和 `kind=job_run` 各若干条。
   - 断言：`memory_nav(kind="job_run")` 只返回 job_run 相关 scope；`memory_list(scope=..., kind="note")` 只返回 note。

3. **ttl 过期清理**
   - 前置：写入 `ttl="1s"` 的条目，等待 2 秒，调用 `gc()`。
   - 断言：该条目从 index.json 和 entries/ 中被清理。

4. **parent_id 关联**
   - 前置：写入日报条目 MEM-A，再写入周报条目 MEM-B（parent_id=MEM-A）。
   - 断言：`memory_get(MEM-B)` 返回中包含 `parent_id: MEM-A`。

5. **job_state 精简**
   - 前置：执行一个定时任务。
   - 断言：`job_states/<job_id>.json` 包含 `last_entry_id`、`run_count`、`consecutive_failures`；不包含 `last_run_id`、`last_error`、`last_trigger`。

6. **ContextRenderer 输出一致性**
   - 前置：同一项目，分别调用 `render_base_brief()` 和 `render_job_context()`。
   - 断言：`render_job_context()` 输出包含 `render_base_brief()` 的全部内容，外加 job 特有部分。

7. **Profile 可插拔**
   - 前置：注册一个自定义 ProfileBuilder，调用 `refresh_profiles()`。
   - 断言：`profiles/` 下生成对应的 `.current.json` 和 `.history.jsonl`。

8. **autoplan 使用新 Store**
   - 前置：运行 `radar.autoplan`。
   - 断言：autoplan 能读取 entries 中的 `kind=job_run` 记录作为 recent_runs 上下文。

### 14.2 兼容性验收

1. **分轨兼容（不双读）**
   - 前置：存在 `.project_memory/knowledge/entries/` 下旧条目，同时新链路写入 `.project_memory/entries/` 新条目。
   - 断言：`ProjectMemoryStore` 只读取新路径；agent chat 仍按旧链路正常读取旧路径；两边互不双读。

2. **agent chat 不受影响**
   - 前置：正常 chat 对话。
   - 断言：system prompt 中的 memory brief 正常显示；`memory_brief` tool 正常工作。

3. **可选双写开关**
   - 前置：开启 `mirror_legacy_memory=true`，执行一次定时任务。
   - 断言：新路径存在 `kind=job_run` 条目，旧路径可见镜像条目；关闭开关后不再产生旧路径镜像。

4. **命令兼容**
   - 断言：`/radar status|jobs|bootstrap|run|autoplan run` 保持可用。

### 14.3 鲁棒性验收

1. index.json 损坏时：降级为空列表，不阻断任务执行。
2. gc() 过程中新写入：不影响新写入的条目。
3. `gc(protect_job_state_refs=True)` 时：`job_states/*.json` 中 `last_entry_id` 指向的条目不会被删。
4. 并发 10 次 `add()`：`MEM-ID` 无重复，index 无损坏。
5. ProfileBuilder 异常：跳过该 builder，不影响其他 builder。

---

## 15. 交付清单

### 15.1 新建文件

| 文件 | 说明 |
|------|------|
| `core/memory/__init__.py` | 模块导出 |
| `core/memory/store.py` | ProjectMemoryStore |
| `core/memory/context_renderer.py` | ContextRenderer |
| `core/memory/profile_builder.py` | ProfileBuilder 协议 |
| `core/memory/builders/__init__.py` | builders 模块 |
| `core/memory/builders/tex_research.py` | TexResearchProfileBuilder |
| `core/memory/builders/chat_preference.py` | ChatPreferenceProfileBuilder |

### 15.2 修改文件

| 文件 | 变化 |
|------|------|
| `core/automation/runtime.py` | 改用 ProjectMemoryStore + ContextRenderer |
| `core/automation/executor.py` | 改用 ContextRenderer |
| `core/automation/store_fs.py` | 删除 runs 方法，更新路径 |
| `agent/radar_autopilot/autoplan.py` | 改用 ProjectMemoryStore |
| `agent/tools/memory_tools.py` | 新增 kind/ttl/parent_id 参数 |
| `core/automation/radar_defaults.py` | 更新 prompt |
| `core/automation/__init__.py` | 更新导出 |

### 15.3 废弃（标记但不删除）

| 文件/方法 | 说明 |
|-----------|------|
| `core/automation/prompt_context.py` | 被 ContextRenderer 替代 |
| `FSAutomationStore.add_run()` | 被 ProjectMemoryStore.add() 替代 |
| `FSAutomationStore.list_runs()` | 被 ProjectMemoryStore.list_by_scope(kind="job_run") 替代 |

---

## 16. 可执行实现清单（接口签名 + 迁移伪代码 + 回滚策略）

### 16.1 实施开关（建议）

```python
# core/automation/settings.py
USE_UNIFIED_MEMORY_FOR_AUTOMATION = True
MIRROR_LEGACY_MEMORY = False   # 仅兼容观测；开启后允许新旧双写
GC_PROTECT_JOB_STATE_REFS = True
```

### 16.2 接口签名（落地版）

```python
# core/memory/store.py
class ProjectMemoryStore(ProjectKnowledgeStore):
    def add(
        self,
        *,
        kind: str = "note",
        scope: str = "project",
        intent: str = "",
        title: str,
        content: str,
        tags: list[str] | None = None,
        source: str = "agent",
        ttl: str | None = None,
        parent_id: str | None = None,
        created_at: str | None = None,
    ) -> str: ...

    def nav(self, domain: str = "all", intent: str = "", kind: str = "", limit: int = 30) -> list[dict[str, Any]]: ...
    def list_by_scope(
        self,
        scope: str,
        *,
        intent: str = "",
        kind: str = "",
        since: str = "",
        limit: int = 20,
        cursor: str = "",
    ) -> dict[str, Any]: ...
    def search(self, query: str, *, kind: str = "", scope: str = "", top_k: int = 5) -> list[dict[str, Any]]: ...
    def gc(self, now: datetime | None = None, *, protect_job_state_refs: bool = True) -> int: ...

    # 并发保护
    def _file_lock(self, name: str = "index.lock"): ...
    def _next_memory_id_from_records(self, records: list[dict[str, Any]]) -> str: ...
```

```python
# core/memory/context_renderer.py
class ContextRenderer:
    def render_base_brief(self, index_limit: int = 12) -> str: ...
    def render_job_context(self, job: AutomationJob, job_state: dict[str, Any], recent_entries: list[dict[str, Any]]) -> str: ...
    def render_autoplan_context(
        self,
        jobs: list[dict[str, Any]],
        states: dict[str, dict[str, Any]],
        recent_entries: list[dict[str, Any]],
    ) -> str: ...
```

```python
# core/automation/runtime.py
async def _run_and_log(self, project: Project, job: AutomationJob, trigger: str) -> Any: ...
def _update_job_state_and_memory(...)-> None: ...

# 行为约束：
# 1) 主写：ProjectMemoryStore.add(kind="job_run", ...)
# 2) 状态：update_job_state(last_entry_id/run_count/consecutive_failures)
# 3) 可选镜像：MIRROR_LEGACY_MEMORY=True 时写旧 ProjectKnowledgeStore
```

```python
# agent/tools/memory_tools.py
class MemoryNavTool:   # +kind 参数
class MemoryListTool:  # +kind 参数
class MemoryWriteTool: # +ttl +parent_id 参数
```

### 16.3 迁移伪代码

#### 16.3.1 一次性迁移 runs -> entries（仅自动化链路）

```python
def migrate_runs_to_unified_entries(project):
    old_store = FSAutomationStore(project)           # 读取 .project_memory/automation/runs
    new_store = ProjectMemoryStore(project)          # 写入 .project_memory/entries

    if marker_exists(".project_memory/.migrations/runs_to_entries.v1.done"):
        return {"migrated": 0, "skipped": "already_done"}

    migrated = 0
    run_map = {}   # (job_id, run_id) -> mem_id
    for run in old_store.list_runs(limit=100000)[::-1]:  # 按时间正序回放
        if not run.get("job_id"):
            continue
        mem_id = new_store.add(
            kind="job_run",
            scope=f"job:{run['job_id']}",
            intent="job_progress",
            title=f"{run['job_id']} run @ {(run.get('ended_at') or run.get('started_at') or '')[:16]}",
            content=render_run_note(run),
            tags=["automation", f"job:{run['job_id']}", f"status:{run.get('status','unknown')}"],
            source="migration:runs_to_entries",
            ttl="30d",
            created_at=run.get("started_at") or run.get("ended_at"),
        )
        run_map[(run["job_id"], run.get("run_id", ""))] = mem_id
        migrated += 1

    # 回填 state 指针（best-effort）
    for job in old_store.list_jobs():
        state = old_store.get_job_state(job.id)
        run_id = str(state.get("last_run_id", "")).strip()
        if run_id and (job.id, run_id) in run_map:
            state["last_entry_id"] = run_map[(job.id, run_id)]
        state.pop("last_run_id", None)
        old_store.update_job_state(job.id, normalize_state(state))

    write_marker(".project_memory/.migrations/runs_to_entries.v1.done")
    return {"migrated": migrated}
```

#### 16.3.2 启动时行为

```python
def bootstrap_project(project):
    if USE_UNIFIED_MEMORY_FOR_AUTOMATION:
        migrate_runs_to_unified_entries(project)   # 幂等
        memory_store = ProjectMemoryStore(project)
        memory_store.refresh_profiles()
    else:
        legacy_ks = ProjectKnowledgeStore(project)
        legacy_ks.refresh_default_profiles()
```

### 16.4 失败回滚策略

#### 16.4.1 回滚触发条件

- 连续 3 次自动化运行失败且根因为 memory 路径/序列化错误。
- index 写入冲突在重试后仍失败。
- 线上观测到 autoplan 上下文缺失关键运行记录。

#### 16.4.2 快速回滚步骤（< 5 分钟）

```python
USE_UNIFIED_MEMORY_FOR_AUTOMATION = False
MIRROR_LEGACY_MEMORY = True
```

执行效果：
- 自动化立即退回旧链路：`FSAutomationStore.add_run()` + `ProjectKnowledgeStore.add_entry()`
- 新链路数据不删除，仅停止写入（保留后续再迁移）
- agent chat 始终不受影响（本来就走旧路径）

#### 16.4.3 回滚后的数据修复

```python
def replay_unified_job_runs_to_legacy(project, since: str):
    new_store = ProjectMemoryStore(project)
    old_ks = ProjectKnowledgeStore(project)
    scopes = new_store.nav(domain="job", kind="job_run", limit=1000)
    for row in scopes:
        scope = str(row.get("scope", "")).strip()
        if not scope:
            continue
        rows = new_store.list_by_scope(scope=scope, kind="job_run", since=since, limit=100000)["items"]
        for item in rows:
            old_ks.add_entry(
                kind="job_run",
                intent=item.get("intent", "job_progress"),
                scope=item.get("scope", ""),
                title=item.get("title", ""),
                content=new_store.get(item["id"]).get("content", ""),
                tags=item.get("tags", []),
                source="rollback_replay",
            )
```

说明：回滚只切换写入路径，不回删新路径数据；恢复时可基于 `since` 增量补齐。

### 16.5 执行顺序（建议）

1. 先落地 `ProjectMemoryStore` + 锁 + `gc` 指针保护（不改调用方）。
2. 改 `runtime.py`（主写新 store，可选镜像旧 store）。
3. 改 `executor.py` 与 `autoplan.py` 的上下文来源。
4. 改 `memory_tools.py` 参数扩展（kind/ttl/parent_id）。
5. 运行第 14 节全部验收，再决定是否开启 `MIRROR_LEGACY_MEMORY`。
