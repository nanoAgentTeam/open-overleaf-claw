# ContextBot 端到端 (E2E) 测试指南

本目录包含 ContextBot 的端到端 (E2E) 测试框架。它允许基于预定义的场景运行完整的 Agent 会话，还可以选择使用 LLM 裁判进行评估。

## 📂 目录结构

- **`cases/`**: 定义测试场景的 YAML 配置文件 (例如 `w03_write_intro.yaml`)。
- **`scripts/`**: 用于执行和评估测试的 Python 脚本。
  - `run_batch.py`: 运行测试的主要入口点。
  - `run_eval.py`: 运行单个测试用例的逻辑。
  - `judge_eval.py`: 基于 LLM 的评估逻辑。
- **`runs/`**: 存储测试执行的产物（快照、日志、修改后的工作区）。
- **`results/`**: 存储裁判生成的 Markdown 评估报告。

## 🛠️ 环境准备

在开始运行测试之前，你需要确保本地开发环境与 Overleaf 测试账号已同步，需通过Overleaf测试账号下全部Project。

### 1. 登录 Overleaf

ContextBot 需要访问你的 Overleaf 账号。

1. 在浏览器（Chrome/Firefox）中登录 Overleaf。
2. 运行登录命令以捕获 Cookie：

```bash
python cli/main.py login
```

（如果缺少 `browsercookie`，请先安装：`pip install browsercookie`）

### 2. 同步测试项目

将本地定义的测试用例 fixtures 同步到 Overleaf 并自动更新 YAML 配置中的 `overleaf_id`：

```bash
python tests/scripts/sync_to_overleaf.py
```

这会确保测试账号中存在对应的 Overleaf 项目，并将该项目的 ID 写入本地配置文件。

## 🚀 CLI 启动方式

### Agent 命令（主要入口）

```bash
python cli/main.py agent [OPTIONS]
```

| 参数              | 说明                                             | 默认值               |
| ----------------- | ------------------------------------------------ | -------------------- |
| `-m, --message` | 发送给 Agent 的消息                              | 无（交互模式）       |
| `-p, --project` | 项目 ID                                          | `Default`          |
| `-s, --session` | Session ID                                       | 自动生成 `MMDD_NN` |
| `-v, --verbose` | 启用 DEBUG 日志                                  | `false`            |
| `--new-session` | 强制创建新 session                               | `false`            |
| `--e2e`         | E2E 自动模式（新 session + 跳过确认 + 自动退出） | `false`            |

### 不同模式的启动示例

**Chat 模式**（Default 项目，通用问答）：

```bash
# 交互式
python cli/main.py agent

# 带消息
python cli/main.py agent -m "帮我搜索最新的 LLM 推理论文"
```

**Project 模式**（进入具体项目，完整工具集）：

```bash
# 交互式，进入 MyPaper 项目
python cli/main.py agent -p MyPaper

# 指定 session 恢复之前的工作
python cli/main.py agent -p MyPaper -s 0226_01

# 带消息，自动创建新 session
python cli/main.py agent -p MyPaper --new-session -m "帮我检查 main.tex 的编译错误"
```

**Task 模式**（自主任务分解与执行）：

```bash
# 在消息中使用 /task 命令触发
python cli/main.py agent -p MyPaper -m "/task 帮我写 Introduction"

# E2E 自动模式（测试用）
python cli/main.py agent -p MyPaper -s test_session --e2e -m "/task 帮我写 Introduction"
```

### 模式自动切换规则

| 条件                           | Profile                | Mode   |
| ------------------------------ | ---------------------- | ------ |
| `-p Default` 或不指定 `-p` | `chat_mode_agent`    | CHAT   |
| `-p <项目名>`                | `project_mode_agent` | NORMAL |
| 消息中包含 `/task`           | `project_task_agent` | TASK   |

## 🧪 运行 E2E 测试

主要的脚本是 `tests/scripts/run_batch.py`。你应该从项目根目录运行它。

### 1. 运行所有测试

执行 `tests/cases/` 中所有可用的测试用例：

```bash
python tests/scripts/run_batch.py
```

### 2. 运行特定测试

运行匹配特定关键字（文件名包含该子串）的用例：

```bash
python tests/scripts/run_batch.py w03 w05
```

### 3. 按类别过滤

仅运行 "写作" (`w*`) 类用例：

```bash
python tests/scripts/run_batch.py --filter w
```

仅运行 "研究" (`r*`) 类用例：

```bash
python tests/scripts/run_batch.py --filter r
```

### 4. 并行执行

并发运行测试以节省时间（例如，3 个 worker）：

```bash
python tests/scripts/run_batch.py --workers 3
```

### 5. 使用 LLM 裁判运行

执行后自动使用 LLM 评估 Agent 的表现（需要配置 API Key）：

```bash
python tests/scripts/run_batch.py --judge
```

组合示例（使用 5 个 worker 运行所有写作类用例并进行评估）：

```bash
python tests/scripts/run_batch.py --filter w --workers 5 --judge
```

## 📝 创建新测试

要添加新的测试用例，请在 `tests/cases/` 中创建一个 `.yaml` 文件。

**配置示例 (`tests/cases/my_test.yaml`):**

```yaml
name: "my_test_case"
project_id: "E2E_Test_MyCase"
mode: "TASK"              # "NORMAL" 用于项目模式，"TASK" 用于自主任务模式
timeout_sec: 10800        # 最大持续时间（秒），默认 3 小时

# 发送给 Agent 的提示词
query: "帮我写一个摘要"

# 可选：要同步的 Overleaf ID（如果测试涉及有效的 Overleaf 项目）
overleaf_id: ""

# 可选：主 tex 文件名
main_tex: "main.tex"

# 用于 LLM 裁判评估
expected_outcome:
  - "Agent 读取了 main.tex 文件。"
  - "Agent 正确生成了摘要。"
```

### 超时配置

- 默认超时：10800 秒（3 小时）
- 可在 YAML 中通过 `timeout_sec` 字段覆盖
- Task 模式涉及多 Worker 并行，建议保持较长超时

## 📊 查看结果

### 执行产物

每次运行都会在 `tests/runs/YYYYMMDD_HHMMSS/` 中创建一个带有时间戳的目录。
其中包含：

- `workspace/`: 测试后项目工作区的完整状态。
- `stdout.txt`: Agent 的控制台输出。
- `run_result.json`: 有关运行的元数据（状态、持续时间等）。

### Worker 产出

Task 模式下，Worker 的产出在 `workspace/<session_id>/_task_workers/` 中：

```
_task_workers/
├── t1_r1/          # task 1, round 1 的变更文件（仅 diff，不含未修改的 core 文件）
├── t2_r1/
└── ...
```

### 评估报告

如果使用 `--judge` 运行，评估报告将保存在 `tests/runs/<timestamp>/<case>/evaluation.md` 中，并在摘要输出中引用。
