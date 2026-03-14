# 研究雷达自动化（Phase-1 可实现蓝图）

> 版本：Phase-1 Blueprint（更新）  
> 日期：2026-02-23  
> 目标：在当前工程中，以“最小控制面 + 自然语言内容面”的方式落地研究雷达

---

## 1. 设计目标

1. 所有雷达能力都由通用定时任务承载，任务核心保持最小：`prompt + type(normal/task) + schedule`。
2. 画像/记忆是通用能力，不绑死在任务模型字段中；通过 prompt 约束 + memory tool 使用。
3. 系统自动加载“压缩记忆背景 + ID 索引”，详情按需 `memory_get(MEM-xxxx)` 渐进披露。
4. 用系统任务 `radar.autoplan` 自动编排雷达任务，输入至少包含：
   - 项目当前内容（Overleaf/tex 语义）
   - 用户交互偏好（从会话中抽取）
   - 现有雷达任务与近期运行状态
5. 输出策略默认不自动推送，只有模型判断“需要通知”时才显式调用 `notify_push`。

---

## 2. 核心原则（本次更新）

1. 控制面结构化最小化：仅保留机器必须要用的调度与变更字段。
2. 内容面自然语言化：任务输出、任务状态解释、memory 写入内容都不做硬 schema 限制。
3. memory 写入轻约束：通过 `memory_write(intent, scope, title, content, tags)` 表达”写入意图”，而不是预定义固定字段集。
4. 自动化状态最小落盘：`last_run_at / last_status / last_entry_id / run_count / consecutive_failures`。
5. `frozen` 是唯一权限边界：`frozen=True` 的任务 autoplan 不可修改，无论 `managed_by` 是什么。
6. `managed_by` 是纯来源标记（`system | user`），不承担权限控制。
7. 任务来源细节记录在 `metadata.origin`（如 `radar_defaults` / `autoplan` / `user`），不引入额外模型字段。

---

## 3. 架构总览

```text
Gateway(cli gateway)
  └─ AutomationRuntime
       ├─ APSSchedulerWrapper
       ├─ FSAutomationStore
       │   ├─ jobs/*.json
       │   ├─ job_states/*.json
       │   └─ subscriptions.json
       ├─ AutomationExecutor
       │   └─ AutomationPromptContextBuilder
       │       ├─ research_core/user_preference
       │       ├─ research trajectory
       │       ├─ recent runs + job_state
       │       └─ compact memory index (ID)
       └─ RadarAutoplanService
            └─ 基于项目画像+偏好+现有任务生成 operations(JSON)

ProjectMemoryStore (.project_memory)
  ├─ index_compact.md
  ├─ index.json
  ├─ entries/MEM-xxxx.md
  ├─ profiles/*.current.json + *.history.jsonl
  └─ job_states/*.json
```

---

## 4. 数据模型（最小控制面）

## 4.1 AutomationJob（保持简洁）

- `id`
- `name`
- `type`: `normal | task`
- `schedule.cron`
- `schedule.timezone`
- `prompt`
- `enabled`
- `managed_by`: `system | user`（纯来源标记，不做权限控制）
- `frozen`: `bool`（默认 `false`，用户锁定开关，`true` 时 autoplan 不可修改）
- `output_policy`（默认 `mode=default`）
- `metadata`（可选，含 `origin` 字段标记创建来源）

说明：
- 不再引入 `memory_bindings`。
- memory 的选择/使用写在任务 prompt 中。
- 删除 `parent_job_id`，来源信息统一记录在 `metadata.origin`。

## 4.2 frozen 与 autoplan 权限控制

### 4.2.1 权限模型

`frozen` 是 autoplan 的唯一权限边界：

| `frozen` | autoplan 能改 | 说明 |
|----------|-------------|------|
| `false` | 能 | 默认状态，autoplan 可优化此任务（不论 managed_by） |
| `true` | 不能 | 用户已锁定，autoplan 跳过 |

`managed_by` 不参与权限判断，仅标记”谁创建的”。

### 4.2.2 autoplan 新建任务策略

通过项目配置控制 autoplan 是否可以新建任务：

```yaml
# project.yaml
automation:
  autoplan:
    enabled: true
    schedule: “0 */12 * * *”
    can_create: true        # autoplan 是否可新建任务
    max_system_jobs: 8      # system 任务总数上限
```

autoplan upsert 行为：

```text
目标 job 已存在？
  ├─ 是 → frozen?
  │       ├─ true  → 跳过
  │       └─ false → 允许更新
  └─ 否 → can_create?
          ├─ false → 跳过
          └─ true  → system 任务数 < max_system_jobs?
                     ├─ 是 → 创建（managed_by=system, metadata.origin=autoplan）
                     └─ 否 → 跳过
```

autoplan disable 行为：

```text
frozen?
  ├─ true  → 跳过
  └─ false → 允许禁用
```

### 4.2.3 用户操作

```text
/radar freeze <job_id>              → frozen=true（从 autoplan 手中收回）
/radar unfreeze <job_id>            → frozen=false（交还给 autoplan 管理）
/radar disable <job_id>             → enabled=false, frozen=true（关掉并锁定）
/radar enable <job_id>              → enabled=true（不自动 freeze）
/radar freeze-all-autoplan          → 所有 metadata.origin=autoplan 的任务 frozen=true
```

### 4.2.4 metadata.origin 约定

| origin 值 | 说明 |
|-----------|------|
| `radar_defaults` | 由 `radar_defaults.py` 模板初始化 |
| `autoplan` | 由 `radar.autoplan` 自动生成 |
| `user` | 用户手动创建 |
| `system` | 系统内置（如 `radar.autoplan` 自身） |

## 4.3 JobState（最小）

`job_states/<job_id>.json` 建议至少包含：
- `last_run_at`
- `last_status`
- `last_entry_id`（指向最近 `MEM-xxxx`）
- `run_count`
- `consecutive_failures`

可扩展字段允许存在，但不作为强约束。

---

## 5. Memory/画像设计（通用 Tool 能力）

## 5.1 渐进披露

1. 系统提示自动加载 `memory brief`：
   - 项目研究快照（topic/stage/keywords）
   - 用户偏好快照（push_style/language/focus）
   - 研究方向近期轨迹
   - memory ID 索引
2. 全文不进 system prompt，按需使用：
   - `memory_nav(domain, intent)`（先找 scope）
   - `memory_list(scope, intent, since, cursor)`（在 scope 内分页看卡片）
   - `memory_get(id)`
3. `memory_search(query)` 仅作为兜底，不再作为主路径。

## 5.2 memory 写入策略（松耦合）

使用 `memory_write` 时推荐填写：
- `intent`：例如 `job_progress` / `research_direction` / `user_preference` / `insight`
- `scope`：例如 `project` / `job:radar.daily.scan`

这两个参数是引导信息，不做强枚举限制，保留任务泛化能力。

## 5.3 自动沉淀

任务每次运行后，runtime 自动把运行摘要写成 `kind=job_run` memory entry（`MEM-xxxx`），并回填到 `job_state.last_entry_id`。

---

## 6. 任务执行语义

## 6.1 Prompt 拼装

执行前系统会把以下内容拼入任务上下文：
1. 任务约束（默认不推送、需要时再 `notify_push`）
2. memory 使用约束（主路径 `memory_nav -> memory_list -> memory_get`）
3. 项目研究快照 + 用户偏好 + 研究方向轨迹
4. 当前任务最近运行记录与 job_state

这样做到：
- 不把输入/输出钉死在 rigid schema；
- 但让模型在一致上下文里做判断。

## 6.2 推送策略

- 默认不推送。
- 只有任务执行中显式调用 `notify_push` 才会发送。
- `notify_push` 未传 `channels` 时，走启用中的默认渠道 + 项目订阅 chat_id。

---

## 7. radar.autoplan 设计（自动编排）

## 7.1 输入

- `research_core`
- `user_preference`
- `research_trajectory`
- `compact_memory_index`
- `existing_jobs`
- `existing_job_states`
- `recent_job_run_entries`

## 7.2 输出（仅控制面结构化）

仍要求 JSON（便于自动应用），但放松字段约束：
- 顶层：`decision/reason/operations`
- `operations` 支持 `upsert/disable`
- `upsert.job` 允许部分字段；系统会用现有值/默认值补齐

说明：
- autoplan 可以少给字段（例如只改 `prompt` 或只改 `schedule`）。
- 应用层做 normalize 与兜底，避免因 schema 过严导致编排失败。
- `frozen` 字段不属于 LLM 可控输出字段，由执行层维护。

## 7.3 安全约束

1. `frozen=true` 的任务一律跳过（不论 managed_by）。
2. 新建任务受 `can_create` 和 `max_system_jobs` 限制。
3. 越权或非法操作直接跳过。
4. 计划解析失败回退 `no_change`。

---

## 8. 调度与运行机制

## 8.1 启动

- `context_bot gateway` 启动时初始化 `AutomationRuntime`。
- Runtime 扫描 `workspace/*/.project_memory/jobs/*.json` 并注册 cron。
- 若项目没有 `radar.autoplan`，自动生成默认系统任务。
- 若项目除了 `radar.autoplan` 外没有其他活跃雷达任务，自动补齐默认模板任务：
  - `radar.daily.scan`（日扫）
  - `radar.weekly.digest`（周报）
  - `radar.urgent.alert`（紧急预警）
  - `radar.direction.drift`（方向漂移）

## 8.2 执行链路

1. APScheduler 到点触发 job。
2. Executor 创建项目级 `AgentLoop` 执行 prompt。
3. 写入运行摘要到 memory entry（`kind=job_run`, `scope=job:<job_id>`）。
4. 写入最小 job_state 到 `.project_memory/job_states/*.json`。
5. 自动回填 `last_entry_id/run_count/consecutive_failures`。
6. 若任务是 `radar.autoplan` 且成功，应用变更并重调度该项目。
7. autoplan 新建任务时写入 `metadata.origin=autoplan`，`managed_by=system`，`frozen=false`。

## 8.3 手动落地模板

- `/radar bootstrap`：合并安装默认模板（不清理现有系统雷达任务）。
- `/radar bootstrap replace`：安装默认模板并禁用其他系统雷达任务（保留用户任务）。

---

## 9. 与 PRD/Benchmark 目标对齐（研究雷达）

Phase-1 侧重“可运行基础设施 + 自动编排”，覆盖 PRD 中雷达地基需求：
1. 有调度能力（定时任务）
2. 有项目画像/偏好画像
3. 有主动推送工具（显式触发）
4. 有系统自编排机制（基于项目内容与用户交互）

在此基础上，R01/R09/R14 等样本可通过“任务 prompt 演进 + autoplan 持续改写”逐步逼近目标效果。

---

## 10. 验收测试方案（Phase-1）

## 10.1 功能验收

1. **自动化任务最小模型**
   - 前置：创建一个 system job。
   - 断言：job JSON 不含 `memory_bindings`，且可正常调度执行。

2. **memory 渐进披露**
   - 前置：写入若干 memory entry。
   - 断言：system prompt 自动出现 brief + MEM ID；全文需 `memory_get` 才可见。

3. **memory 分层导航**
   - 前置：在不同 scope 下写入 memory（如 `job:radar.daily.scan`、`project`）。
   - 断言：`memory_nav(domain='job')` 可返回 scope 目录；`memory_list(scope=...)` 可按时间分页返回卡片。

4. **memory 写入意图参数**
   - 前置：调用 `memory_write(intent="job_progress", scope="job:xxx", ...)`。
   - 断言：index 记录可见 intent/scope；`memory_search` 可搜到。

5. **任务执行上下文增强**
   - 前置：同一 job 连续运行两次。
   - 断言：第二次执行上下文可见最近 `kind=job_run` 记录与 `last_entry_id`。

6. **推送显式触发**
   - 前置：任务 prompt 不调用 `notify_push`。
   - 断言：无 outbound 推送。
   - 再测：任务显式调用 `notify_push`。
   - 断言：发送到已订阅 chat_id。

7. **autoplan 放松结构化输入**
   - 前置：让 autoplan 返回“部分字段 upsert”。
   - 断言：系统可 normalize 并落盘有效 job。

8. **autoplan 权限隔离（frozen）**
   - 前置：将某任务 `frozen=true`。
   - 断言：autoplan 对其 upsert/disable 操作被跳过。
   - 再测：`/radar unfreeze` 后，autoplan 可再次修改该任务。

9. **autoplan 后即时重调度**
   - 前置：autoplan 修改某系统任务 cron。
   - 断言：scheduler 使用新 cron 生效（旧 key 被替换）。

10. **autoplan 新建任务受限**
    - 前置：设置 `can_create=true`，`max_system_jobs=2`，已有 2 个 system 任务。
    - 断言：autoplan 尝试新建第 3 个任务时被跳过。
    - 再测：设置 `can_create=false`。
    - 断言：autoplan 尝试新建任务时被跳过，但更新已有任务正常。

11. **freeze/unfreeze 用户操作**
    - 前置：`/radar freeze <job_id>`。
    - 断言：job JSON 中 `frozen=true`。
    - 再测：`/radar unfreeze <job_id>`。
    - 断言：job JSON 中 `frozen=false`。

12. **metadata.origin 标记**
    - 前置：通过 autoplan 新建一个任务。
    - 断言：`metadata.origin="autoplan"`。
    - 前置：通过 `/radar bootstrap` 初始化模板任务。
    - 断言：`metadata.origin="radar_defaults"`。

## 10.2 鲁棒性验收

1. APScheduler 缺失时：系统告警但主流程不中断。
2. autoplan 输出非 JSON：回退 `no_change`。
3. memory 文件损坏：降级为空，不阻断任务执行。
4. notify_push 失败：记录错误，不影响 job status 记录。

## 10.3 回归验收

1. `/radar status|jobs|bootstrap|run|autoplan run|freeze|unfreeze` 保持可用。
2. 普通 CHAT/TASK 流程不受影响。
3. 现有 tools 注册与命令加载不报错。

---

## 11. Phase-1 交付清单（代码）

1. `core/automation`: runtime/scheduler/store/executor/prompt_context
2. `core/memory`: unified project memory store + context renderer + profiles
3. `agent/tools/memory_tools.py`: `memory_nav/list/get/search/write/brief`, `profile_read/refresh`
4. `agent/tools/notify.py`: 显式推送能力
5. `agent/radar_autopilot/autoplan.py`: 自动编排与 normalize
6. `agent/context.py`: system prompt 自动加载 memory brief

---

## 12. 后续（Phase-2）

1. 增加雷达数据源适配器（OpenReview/CrossRef/会议日历）
2. 加入用户反馈闭环（推送“有用/无用”反哺 autoplan）
3. 从 FS 平滑迁移到 SQLite（接口保持兼容）
