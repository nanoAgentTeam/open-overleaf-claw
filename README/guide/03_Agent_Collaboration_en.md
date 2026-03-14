# Agent and SubAgent Collaboration

## Main Agent (Assistant Role)

The main Agent is the one you directly interact with. It has full read/write access to the project core. It can:

- Directly read and write paper files (.tex, .bib, etc.)
- Compile LaTeX to generate PDFs
- Create SubAgents and assign tasks

## SubAgent (Worker Role)

SubAgents work in isolated overlay directories and **do not directly modify core**. After task completion, their output is merged through the merge mechanism:

- **merge_to_core = true**: Output is written directly to core, triggering auto commit
- **merge_to_core = false** (current default): Output is written to `core/_subagent_results/{agent_name}/`, for the main Agent to review and decide whether to adopt. In this case, the SubAgent has no core write permission

The merge strategy is configured in `config/agents.json`.

## Collaboration Workflow Example

```
User: "Help me write a paper about MoE"

Main Agent:
  1. Create a researcher SubAgent (literature research expert)
  2. Create a writer SubAgent (paper writing expert)
  3. Assign tasks to researcher → researches in overlay, output merged back
  4. Assign tasks to writer → writes based on research results, output merged back
  5. Main Agent integrates, compiles, and syncs
```

## Research Modes

### Deep Research (/task)

Sequentially executed multi-step tasks:

1. Planner decomposes the task into a DAG (Directed Acyclic Graph), determining dependencies
2. Engine schedules according to dependency order, supporting parallel execution of independent tasks
3. Executor spawns a Worker Agent for each subtask; upon completion, a Reviewer audits the result
4. Failed tasks are automatically retried, and results are aggregated and returned

Suitable for tasks with clear steps and dependency relationships.
