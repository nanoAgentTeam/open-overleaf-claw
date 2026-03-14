# Configuration 设计

## 设计目标

让系统的行为尽可能通过配置文件控制，而不是硬编码。这样调整行为（启用/禁用工具、修改 prompt、切换模型）不需要改代码。

## 三层配置

### 1. 全局配置（settings.json）

运行时的主配置文件，负责描述运行策略和可热更新的运行时参数。

目的：把“运行策略”从代码中抽离，支持通过配置热更新和最小代码改动。

主要用途：

- Agent 默认参数（workspace、模型、迭代参数）
- LLM 实例与激活策略
- IM 账号与激活策略
- Gateway、工具与功能开关

文件加载顺序（当前实现）：

- 优先读取项目根目录的 `./settings.json`
- 若项目根目录不存在 `settings.json`，回退到 `~/.context_bot/config.json`
- `config/features.json` 会单独读取并覆盖到运行时配置的 `features`

建议结构说明：

1) Agent 默认参数

- `agents.defaults.workspace`
- `agents.defaults.model`
- `agents.defaults.maxTokens`
- `agents.defaults.temperature`
- `agents.defaults.maxToolIterations`

2) Provider 统一配置

- `provider.activeId`：当前激活的 LLM 实例 ID
- `provider.instances[]`：可用实例列表，包含：
	- `id`
	- `provider`（如 openai / anthropic / qwen / deepseek / openrouter）
	- `modelName`
	- `apiKey`
	- `apiBase`
	- `enabled`

3) Channel 统一配置

- `channel.activeId`：当前激活 IM 账号 ID
- `channel.accounts[]`：可用 IM 账号列表，包含：
	- `id`
	- `platform`（feishu / telegram / qq / whatsapp）
	- `enabled`
	- `credentials`（按平台差异化）

4) 运行与能力配置

- `gateway.host` / `gateway.port`
- `tools.web.search` / `tools.academic`
- `features.history` / `features.memory` / `features.agent` / `features.project` / `features.tools`

兼容策略

系统采用“统一配置优先，旧字段兼容回填”的策略以平滑迁移：

1. 主路径：优先读取 `provider.*` 与 `channel.*`。
2. 兼容层：`config.sync_from_unified_config()` 会把统一配置同步到旧字段 `providers` / `channels`，供尚未迁移的代码继续使用。
3. 回退路径：当 `channel.accounts` 为空时，IM 运行时可从旧字段 `channels.feishu` / `channels.telegram` 迁移为临时账号并启动。

说明：兼容层用于平滑迁移，不建议新增功能继续依赖旧字段。

推荐最小配置示例：

```json
{
	"agents": {
		"defaults": {
			"workspace": "./workspace",
			"model": "step-3.5-flash",
			"maxTokens": 8192,
			"temperature": 0.7,
			"maxToolIterations": 20
		}
	},
	"gateway": {
		"host": "0.0.0.0",
		"port": 18790
	},
	"provider": {
		"activeId": "step",
		"instances": [
			{
				"id": "step",
				"provider": "openai",
				"modelName": "step-3.5-flash",
				"apiKey": "",
				"apiBase": "https://api.stepfun.com/v1",
				"enabled": true
			}
		]
	},
	"channel": {
		"activeId": "feishu-main",
		"accounts": [
			{
				"id": "feishu-main",
				"platform": "feishu",
				"enabled": true,
				"credentials": {
					"appId": "",
					"appSecret": ""
				}
			}
		]
	}
}
```

安全与提交建议

- 不要把真实 `apiKey`、`appSecret` 提交到仓库。
- 建议仓库内保留脱敏配置，个人环境使用本地私有配置覆盖。
- 变更 `settings.json` 结构时，需要同步更新：
	- `config/schema.py`
	- `config/loader.py`
	- `cli/wizard.py`（若涉及向导交互）
	- 对应 README 指南文档

相关代码位置

- `config/schema.py`：配置模型定义
- `config/loader.py`：读取、转换（camel/snake）、保存与兼容同步
- `agent/services/im_runtime.py`：IM 账号运行时装载与旧配置回退迁移
- `providers/proxy.py`：按活动实例动态代理 LLM Provider


### 2. 功能配置（config/features.json）

功能开关和参数：

- History：加载多少条历史消息、auto-summary 的触发阈值
- Memory：是否启用长期记忆
- Agent：最大迭代次数、token 预算

### 3. 项目配置（workspace/{project}/project.yaml）

项目级别的配置：

- Git：是否启用 auto_commit
- Overleaf：project_id、是否自动 pull
- LaTeX：编译命令、主文件路径

## ConfigRegistry

系统有一个中心化的 ConfigRegistry，负责加载和管理所有配置文件：

| 配置文件                 | 用途                              |
| ------------------------ | --------------------------------- |
| `config/tools.json`    | 工具注册表                        |
| `config/commands.json` | 斜杠命令定义                      |
| `config/roles.json`    | 角色和权限定义                    |
| `config/agents.json`   | SubAgent 配置                     |
| `config/modes.json`    | 模式定义（CHAT/NORMAL/TASK/TEAM） |
| `config/vfs.json`      | 路径和记忆路径                    |
| `config/prompts/*.txt` | Prompt 模板                       |

## Prompt 模板

System prompt 的各个片段存储在 `config/prompts/` 下的文本文件中，支持变量替换（`{{project_name}}`、`{{session_id}}` 等）。

这让修改 Agent 的行为指引不需要改 Python 代码。

## 关键设计决策

**为什么分三层？** 不同配置的变更频率不同。settings.json 部署时配一次，features.json 偶尔调整，project.yaml 每个项目不同。分层让管理更清晰。

**为什么用 JSON 而不是 YAML？** 大部分配置用 JSON 足够，且 Python 原生支持。project.yaml 用 YAML 是因为它更适合人类编辑（项目配置经常需要手动改）。

**为什么 prompt 用独立的文本文件？** prompt 通常很长，放在 JSON 中不方便编辑和阅读。独立文件可以用任何文本编辑器修改。

## 相关文件

- `config/loader.py` — 配置加载器
- `config/schema.py` — 配置 schema（Pydantic 模型）
- `config/registry.py` — ConfigRegistry
- `config/prompts/` — Prompt 模板目录
