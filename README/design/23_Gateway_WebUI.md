# Gateway & Web UI

> 版本：v1
> 日期：2026-02-28
> 前置：Design 16（Configuration）、Design 19（Research Radar Automation）

---

## 1. 概述

Gateway 是系统的 Web 管理入口，包含 5 个核心模块：

| 模块 | 文件 | 职责 |
|------|------|------|
| Gateway Server | `agent/services/gateway_server.py` | FastAPI 后端，REST API + WebSocket |
| Web UI | `static/ui/index.html` | Alpine.js + Tailwind CSS 单页应用 |
| Wizard | `cli/wizard.py` | Rich 终端交互式配置向导 |
| DynamicProviderProxy | `providers/proxy.py` | LLM Provider 运行时热切换 |
| ConfigService | `config/loader.py` | 统一配置读写（单例） |

---

## 2. 启动方式

```bash
# 交互式向导（推荐首次使用）
python cli/main.py onboard

# 直接启动 Gateway
python cli/main.py gateway --port 18790

# 系统诊断
python cli/main.py doctor

# CLI 交互式 Agent
python cli/main.py agent

# E2E 自动化模式
python cli/main.py agent --e2e
```

Gateway 启动后 Web UI 访问：`http://127.0.0.1:18790/ui`

---

## 3. Gateway Server

FastAPI 后端，提供 REST API + WebSocket 日志推送。

### 3.1 API 端点

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/config` | GET/POST | 读取/更新配置 |
| `/api/config/backups` | GET | 列出配置备份 |
| `/api/config/backup` | POST | 创建备份 |
| `/api/config/restore` | POST | 恢复备份 |
| `/api/config/test-llm` | POST | 测试 LLM 连通性 |
| `/api/config/test-im` | POST | 测试 IM 凭证 |
| `/api/config/subscriptions` | GET/POST | 管理推送订阅 |
| `/api/config/smtp-profiles` | GET/POST | 管理 SMTP 邮件配置 |
| `/api/diagnostics` | GET | 运行系统诊断 |
| `/api/projects` | GET | 列出所有项目 |
| `/api/projects/{pid}/jobs` | GET/POST/PUT/DELETE | 管理自动化任务 |
| `/api/projects/{pid}/runs` | GET | 列出运行记录（支持 `?job_id=&limit=`） |
| `/api/projects/{pid}/runs/{id}` | GET/DELETE | 查看/删除单条运行记录 |
| `/api/projects/{pid}/jobs/{jid}/run` | POST | 手动触发任务 |
| `/api/projects/{pid}/bootstrap` | POST | 安装默认 radar 任务 |
| `/ws/logs` | WebSocket | 实时日志流 |

### 3.2 启动流程

```
startup_event()
├── AutomationRuntime.start()
│   ├── _bootstrap_all_projects()    # 遍历 workspace/ 下所有项目
│   │   └── bootstrap_project()      # 安装默认 radar jobs + 注册 scheduler
│   └── APScheduler 启动
├── IMRuntime.start_all()            # 启动 IM 通道（飞书/Telegram 等）
└── AgentLoop.run()                  # 启动消息处理循环
```

---

## 4. Web UI

`static/ui/index.html`，Alpine.js + Tailwind CSS 单页应用，无需构建。

页面模块：

| 页面 | 功能 |
|------|------|
| Dashboard | 总览（活跃模型、通道、工作区） |
| Provider 模型 | LLM 实例增删改测试、设置活跃模型 |
| IM 通讯 | Telegram / 飞书 / QQ / WhatsApp 账号管理 |
| 推送订阅 | 通知目标配置（飞书、Telegram、Server酱、邮件、Apprise） |
| SMTP 邮件 | 邮件发送配置（预设 QQ、163、Gmail、Outlook） |
| 自动化任务 | Cron 调度任务管理 |
| 项目管理 | 项目列表 + 任务执行历史 + 运行记录 |
| 系统诊断 | LLM / IM 连通性测试 |
| 配置备份 | 备份/恢复（自动保留最近 15 份） |

---

## 5. Wizard（交互式向导）

`cli/wizard.py`，Rich 终端 UI。

引导配置：
- LLM Provider（Anthropic、OpenAI、DeepSeek、Gemini、Step、OpenRouter、自定义）
- IM 通道（飞书、Telegram、QQ、WhatsApp）
- 工作区路径
- 连通性实时测试

完成后可选：保存并启动 Gateway / 保存并进入 Agent CLI / 仅保存退出。

---

## 6. DynamicProviderProxy（LLM 热切换）

`providers/proxy.py`

代理模式，运行时检测 `provider.activeId` 变更并自动切换底层 LLM 实例，无需重启服务。

支持的 Provider 类型：
- OpenAI 兼容 API（OpenAI、DeepSeek、Step、OpenRouter、vLLM 等）
- Anthropic
- LiteLLM

切换逻辑：每次 LLM 调用前检查 `settings.json` 中 `provider.activeId`，若与当前实例不同则重新初始化。

---

## 7. ConfigService（配置管理）

`config/loader.py`，单例模式。

特性：
- 自动 camelCase ↔ snake_case 转换
- Pydantic 校验（`config/schema.py` 定义所有字段和默认值）
- `sync_from_unified_config()` 桥接新旧配置格式

### 7.1 配置文件结构

`settings.json` 是唯一的配置文件：

```
settings.json
├── agents.defaults      # Agent 默认参数（model、workspace、maxTokens）
├── gateway              # Gateway 服务地址（host、port）
├── providers            # LLM Provider 凭证（旧格式，8 个 provider）
├── channels             # IM 通道凭证（旧格式，4 个 channel）
├── tools                # 工具配置（web search、academic）
├── features             # 功能开关（history、memory、agent、project、tools）
├── provider             # Provider 实例列表（新格式，wizard/UI 写入）
├── channel              # Channel 账号列表（新格式，wizard/UI 写入）
├── pushSubscriptions    # 推送订阅列表
└── smtp                 # SMTP 邮件配置
```

新旧格式共存：`providers`/`channels` 是旧格式，`provider`/`channel` 是新格式。`sync_from_unified_config()` 在加载时将新格式同步到旧格式字段。

---

## 8. Slash 命令（Radar）

`/radar` 命令通过飞书/CLI 管理自动化雷达任务：

| 命令 | 功能 |
|------|------|
| `/radar status` | 查看当前项目 radar 状态 |
| `/radar subscribe` | 订阅当前项目推送到当前聊天 |
| `/radar jobs` | 列出所有自动化任务 |
| `/radar bootstrap [replace]` | 安装/重置默认 radar 任务模板 |
| `/radar run <job_id>` | 手动触发指定任务 |
| `/radar push` | 推送最近一条扫描结果到订阅者 |
| `/radar autoplan run` | 手动触发 autoplan |
| `/radar freeze <job_id>` | 锁定任务（autoplan 不再修改） |
| `/radar unfreeze <job_id>` | 解锁任务 |
| `/radar freeze-all-autoplan` | 锁定所有 autoplan 生成的任务 |
| `/radar disable <job_id>` | 禁用并锁定任务 |
| `/radar enable <job_id>` | 启用任务 |
