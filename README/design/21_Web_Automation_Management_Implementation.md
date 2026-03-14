# Web 定时任务管理实现方案（MVP，已落地）

> 版本：v1.1  
> 日期：2026-02-23  
> 目标：在现有 Gateway + Web UI 基础上，落地项目级定时任务管理与基础运行观测能力。  
> 关联文档：

> - `README/design/17_Task_Mode.md`
> - `README/design/18_Task_Mode_Example.md`
> - `README/PRD/PRD：web、cli管理.md`
>
> ⚠️ 2026-02-25 状态更新：本文为 2026-02-23 的 MVP 阶段记录。当前 `static/ui/index.html` 已扩展到自动化任务手动执行、Autoplan 最近运行、推送订阅（含 SMTP/Email）等能力。请以 `README/guide/09_Web界面功能说明.md` 作为现行事实文档。

---

## 1. 背景与约束

结合现状代码与 PRD，当前系统已有：

- 自动化内核：`core/automation/runtime.py`、`store_fs.py`、`models.py`
- CLI 管理入口：`/radar` 命令（已覆盖 status/jobs/run/freeze/enable/disable 等）
- Web 网关能力：`agent/services/gateway_server.py`（仅配置与诊断 API）
- Web UI：`static/ui/index.html`（仅 dashboard/provider/channel/logs 四个选项卡）

当前缺口是：Web 还没有项目上下文和自动化任务 API，也没有任务管理页面。

---

## 2. 本次实现范围（MVP）

当前已落地能力：

1. 查看任务列表
2. 新增任务
3. 编辑任务（name/type/prompt/schedule）
4. 删除任务
5. 启用任务
6. 停用任务
7. 运行统计（最近开始时间、最近耗时、总执行次数、总执行耗时）
8. 运行历史（列表 + 详情）

### 2.1 暂不纳入 MVP

以下能力保留为下一阶段（P1+）：

- 手动执行任务（run now）
- autoplan 面板
- 订阅管理
- 任务分组联动开关（group toggle）

说明：这些能力在 PRD 已规划，但不影响你当前“可管理任务”的核心诉求。

---

## 3. 设计原则

1. 项目级隔离：所有任务操作必须带 `project_id`。
2. 复用现有控制面：直接基于 `FSAutomationStore` + `AutomationJob`，不新增平行存储。
3. Web 与 CLI 语义一致：`enabled=true/false` 对齐 `/radar enable|disable`，`managed_by` 仅作来源标记。
4. 权限语义：看板权限控制以 `frozen` 与核心任务保护规则为准。
5. 最小侵入：在 `gateway_server.py` 增量扩展 API，不重写网关架构。
6. 即改即生效：更新任务后触发项目重调度（当 Runtime 可用）。

---

## 4. 后端实现

## 4.1 新增网关状态容器

在 `agent/services/gateway_server.py` 增加一个自动化运行时单例，供 API 调用重调度：

- `automation_runtime: AutomationRuntime | None`
- `automation_runtime` 在 startup 时尽量初始化并 `start()`（失败不阻塞 API）
- shutdown 时若存在则 `stop()`（确保优雅退出）

关键约束：

- **任务 API 不依赖 runtime 存在**。即使 runtime 未就绪，也要允许任务 CRUD 落盘；仅在响应中附带 warning。

建议在 startup 顺序中：

1. 初始化 config/bus/provider
2. 启动 `automation_runtime`
3. 启动 IM runtime 和 AgentLoop

## 4.2 新增项目查询 API（MVP 必要）

### `GET /api/projects`

返回最简项目列表，供前端下拉选择：

```json
[
  {
    "id": "manuscript",
    "name": "manuscript",
    "hasAutomation": true
  }
]
```

实现要点：

- 扫描 `config.workspace_path` 目录
- 过滤：隐藏目录、`Default`
- `hasAutomation` 依据 `project.config.automation.enabled`

## 4.3 任务管理 API（MVP）

### 1) 查看任务列表

`GET /api/projects/{pid}/jobs`

返回：

```json
[
  {
    "id": "radar.daily.scan",
    "name": "Radar Daily Scan",
    "type": "normal",
    "schedule": {"cron": "10 9 * * *", "timezone": "UTC"},
    "prompt": "...",
    "enabled": true,
    "managed_by": "system",
    "frozen": false,
    "updated_at": "2026-02-23T10:00:00",
    "metadata": {"origin": "radar_defaults"}
  }
]
```

实现：

- `Project(pid, workspace)`
- `store = FSAutomationStore(project)`
- `return [job.to_dict() for job in store.list_jobs()]`

### 2) 新增任务

`POST /api/projects/{pid}/jobs`

请求体（最简）：

```json
{
  "id": "user.weekly.digest",
  "name": "User Weekly Digest",
  "type": "normal",
  "schedule": {"cron": "0 18 * * 5", "timezone": "UTC"},
  "prompt": "每周总结本项目研究进展..."
}
```

后端补默认值：

- `enabled = true`
- `managed_by = "user"`
- `frozen = false`
- `output_policy = {"mode":"default"}`

校验规则：

- `id` 必填且唯一（若重复返回 409）
- `type in {normal, task}`
- `cron` 合法（可复用 APScheduler `CronTrigger.from_crontab` 验证）
- `prompt` 非空

创建后：

- `store.upsert_job(job)`
- 如果 `automation_runtime` 可用：`await automation_runtime.reschedule_project(project)`

### 3) 启用/停用任务（统一更新接口）

`PUT /api/projects/{pid}/jobs/{job_id}`

MVP 仅要求支持：

- `enabled: true|false`

可同时允许更新（便于后续扩展）：

- `prompt`
- `schedule.cron`
- `schedule.timezone`

规则：

- 任务不存在返回 404
- 更新后 `store.upsert_job(job)`
- 触发 `reschedule_project`

### 4) 删除任务

`DELETE /api/projects/{pid}/jobs/{job_id}`

权限规则：

- `managed_by` 不参与删除权限判断
- 核心任务 `radar.autoplan` 返回 403（防止误删）

流程：

- `store.delete_job(job_id)`
- `reschedule_project`

## 4.4 错误码规范

- `400` 参数非法（cron/prompt/type）
- `404` 项目或任务不存在
- `409` 创建时 ID 冲突
- `403` 删除 system 任务
- `500` 未预期异常（返回 `detail`）

## 4.5 运行历史 API（已实现）

### 1) 运行记录列表

`GET /api/projects/{pid}/runs?job_id=<optional>&limit=50`

能力：

- 支持按任务筛选 `job_id`
- 支持 `limit` 限流（后端上限 200）
- 返回 `started_at / ended_at / duration_seconds / status / run_id`

### 2) 运行记录详情

`GET /api/projects/{pid}/runs/{run_id}`

能力：

- 返回 run 的完整内容（含 summary / error）
- 返回 scope/source 便于排查来源

---

## 5. 前端实现（static/ui/index.html）

## 5.1 侧边栏与状态

在现有菜单中新增：

- `automation`：自动化任务

在侧边栏顶部新增项目选择器：

- `selectedProjectId`
- `projects: []`
- `loadProjects()` 初始化拉取

切换项目时触发：

- `loadJobs(selectedProjectId)`

## 5.2 新增页面结构（Automation Tab）

页面分 4 个区块：

1. 顶部工具栏：项目下拉、刷新按钮、新建任务按钮。
2. 任务表格：列包含 ID、名称、类型、Cron、时区、启用状态、冻结状态、最近开始、最近耗时、总执行次数、总执行耗时、管理来源、操作。
3. 新建任务弹窗：字段为 id/name/type/cron/timezone/prompt。
4. 运行历史区块：任务筛选、记录列表与详情面板。

## 5.3 交互动作映射

- 查看：`GET /api/projects/{pid}/jobs`
- 新增：`POST /api/projects/{pid}/jobs`
- 启停：行内 switch → `PUT ... {enabled: !enabled}`
- 编辑：编辑面板 → `PUT ... {name,type,enabled,prompt,schedule}`
- 删除：删除按钮 → 二次确认 → `DELETE ...`
- 运行历史：`GET /api/projects/{pid}/runs`、`GET /api/projects/{pid}/runs/{run_id}`

## 5.4 UX 细节（MVP）

- 核心任务 `radar.autoplan` 删除按钮置灰并提示不可删除
- 正在请求时行内按钮 `disabled`
- 所有操作完成后 toast 提示 + 刷新列表
- prompt 列表默认不展开，避免页面过长（在弹窗中编辑）

---

## 6. 与 Task Mode / Radar 体系的对齐

- Task Mode 文档（17/18）强调“执行与控制解耦、状态可追踪”，本方案延续该原则：
  - Web 仅操作控制面（job 定义 + enabled）
  - 执行面仍由 `AutomationRuntime` 统一调度
- 与 `/radar` 一致性：
  - 启停语义一致
  - 删除权限一致（用户任务可删，系统任务不可删）

---

## 7. 实施步骤（建议按天拆分）

### Day 1：后端 API

1. `gateway_server.py` 增加 `GET /api/projects`
2. 增加 jobs CRUD 四个接口（GET/POST/PUT/DELETE）
3. 增加 cron 校验与统一错误返回
4. 接入 `automation_runtime.reschedule_project`

### Day 2：前端页面

1. 新增 `automation` 选项卡与项目下拉
2. 实现任务列表加载
3. 实现新建弹窗与提交
4. 实现启停开关和删除按钮

### Day 3：联调与验收

1. API + UI 联调
2. 验证启停后调度生效
3. 验证运行统计字段随任务执行更新
4. 验证运行历史列表与详情可读取
5. 回归现有 tab（dashboard/provider/channel/logs）

---

## 8. 验收标准（MVP）

1. 打开 Web 后可选择项目并看到任务列表。
2. 可成功创建一条任务并正常保存来源标记（`managed_by`/`metadata.origin`）。
3. 任务可在 Web 上启用/停用，刷新后状态持久化。
4. 可编辑任务 name/type/prompt/schedule 并保存成功。
5. 非核心任务可删除；`radar.autoplan` 删除被拒绝（403 + 提示）。
6. 任务行可显示最近开始时间、最近耗时、总执行次数、总执行耗时。
7. 可查看运行历史列表与单条详情。
8. 操作后不需要重启网关，调度状态即时更新。

---

## 9. 风险与应对

1. Runtime 在网关未初始化
   - 应对：API 允许先改存储，再返回 `runtime_not_ready` 警告。
2. cron 表达式误填
   - 应对：后端强校验，前端给示例占位符（如 `0 9 * * *`）。
3. 并发修改冲突
   - 应对：以最后写入为准；后续可加 `updated_at` 乐观锁。

---

## 10. 下一阶段（P1）

在 MVP 稳定后追加：

- 手动执行 `POST /api/projects/{pid}/jobs/{job_id}/run`
- autoplan 面板
- subscriptions 管理
- 任务组联动启停（group）

这样可以平滑对齐 PRD 的完整“自动化任务 + 运行记录 + 项目记忆”路线。
