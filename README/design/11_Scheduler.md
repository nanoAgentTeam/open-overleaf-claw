# Scheduler 设计（Deep Research）

> **注意**：Scheduler 已演进为 Task Mode（SDD 架构）。本文档保留基础概念，完整设计详见 `17_Task_Mode.md`。

## 什么是 Scheduler

Scheduler 是 Deep Research 模式的执行引擎。当用户通过 `/task` 发起一个复杂的调研任务时，系统进入 Task Mode，经历 UNDERSTAND → PLAN → EXECUTE → FINALIZE 四个阶段。

## 核心组件

### Planner（规划器）

接收用户的调研请求，调用 LLM 生成一个 TaskGraph（任务有向无环图）：

- 每个节点是一个子任务，包含描述、验收标准（spec）、预期产出
- 边表示依赖关系（任务 A 完成后才能开始任务 B）
- 无依赖的任务可以并行执行

### BatchRunner（调度引擎）

接收 TaskGraph，按拓扑顺序调度执行：

- 找出所有无依赖的任务，并行启动
- 任务完成后，检查是否有新的任务被解锁
- 重复直到所有任务完成
- 通过 `graph is not` 检查检测 TaskGraph 变化，跨轮次自动重建

### SDDExecutor（执行器）

为每个子任务执行 Worker→Reviewer 循环：

- Worker 在隔离的 overlay 目录中工作（最多 15 步）
- 上游任务产出通过依赖注入复制到 Worker 目录，并设为只读（三层写保护）
- Reviewer 审核产出质量（最多 10 步），知道 Worker 身份、任务目标和依赖目录
- 审核不通过则反馈给 Worker 重做（最多 3 次）
- 通过后 merge 到 `core/_task_workers/{task_id}_r{round_id}/`

## 执行流程

```
用户: /task "调研 MoE 并写综述"
  ↓
[UNDERSTAND] 主 Agent 理解需求
  ↓
[PLAN] Planner 生成 TaskGraph
  ├── task_1: 搜索 MoE 最新论文
  ├── task_2: 搜索 MoE 应用场景（与 task_1 并行）
  ├── task_3: 分析对比（依赖 task_1, task_2）
  └── task_4: 撰写综述（依赖 task_3）
  ↓
[EXECUTE] BatchRunner 并行执行 task_1 + task_2 → task_3 → task_4
  ↓
[FINALIZE] 主 Agent 整合 Worker 产出为最终交付物
  ↓
task_commit → 提交到 git
```

## 持久化

执行计划会保存到 `workspace/tasks/`：
- `latest_plan.json` — 结构化的任务图
- `latest_plan.md` — 可读的 Mermaid 流程图

## 关键设计决策

**为什么用 DAG 而不是简单的顺序列表？** 并行性。很多调研子任务之间没有依赖关系，可以同时执行，显著缩短总耗时。

**为什么有 Reviewer 环节？** 质量保证。Worker 的产出可能不完整或偏题，Reviewer 审核后可以要求重做。

**为什么最多重试 3 次？** 避免无限循环。如果 3 次都不通过，说明任务本身可能有问题，应该返回让用户调整。

**为什么 FINALIZE 要重新整合？** Worker 产出可能包含编译错误或格式不一致。FINALIZE 让主 Agent 审视全局，产出干净的交付物。

## 相关文件

- `agent/scheduler/planner.py` — Planner 实现
- `agent/scheduler/batch_runner.py` — BatchRunner 实现
- `agent/scheduler/executor.py` — SDDExecutor 实现
- `agent/scheduler/schema.py` — 数据模型
- `agent/tools/task_tools.py` — Task 工具集
- `agent/context.py` — 阶段 prompt 定义
- 完整设计：`README/design/17_Task_Mode.md`
