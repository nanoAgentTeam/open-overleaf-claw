# Agent 与 SubAgent 协作

## 主 Agent（Assistant 角色）

主 Agent 是你直接对话的 Agent，它拥有项目 core 的完整读写权限。它可以：

- 直接读写论文文件（.tex、.bib 等）
- 编译 LaTeX 生成 PDF
- 创建子 Agent 并分配任务

## SubAgent（Worker 角色）

子 Agent 在隔离的 overlay 目录中工作，**不直接修改 core**。任务完成后，产出通过 merge 机制合并：

- **merge_to_core = true**：产出直接写入 core，触发 auto commit
- **merge_to_core = false**（当前默认）：产出写入 `core/_subagent_results/{agent_name}/`，供主 Agent 审阅后决定是否采纳。此时 SubAgent 无 core 写入权限

merge 策略在 `config/agents.json` 中配置。

## 协作流程示例

```
用户: "帮我写一篇关于 MoE 的论文"

主 Agent:
  1. 创建 researcher 子 Agent（文献调研专家）
  2. 创建 writer 子 Agent（论文写作专家）
  3. 分配任务给 researcher → 在 overlay 中调研，产出 merge 回来
  4. 分配任务给 writer → 基于调研结果撰写，产出 merge 回来
  5. 主 Agent 整合、编译、同步
```

## 研究模式

### Deep Research（/task）

顺序执行的多步任务：

1. Planner 将任务分解为 DAG（有向无环图），确定依赖关系
2. Engine 按依赖顺序调度，支持并行执行无依赖的任务
3. Executor 为每个子任务 spawn Worker Agent，完成后由 Reviewer 审核
4. 失败自动重试，结果汇总返回

适合有明确步骤和依赖关系的任务。
