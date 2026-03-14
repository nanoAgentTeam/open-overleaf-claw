# Web 界面功能说明（按模块）

本文档描述当前 Web 控制台的功能设计与代码实现映射，覆盖前端页面模块、关键函数、后端 API、以及核心数据流。

## 1. 代码结构与职责

### 1.1 前端

- 文件：`static/ui/index.html`
- 技术：Alpine.js + Tailwind
- 组织方式：单文件页面 + `app()` 状态对象 + 按 tab 的模块视图
- 核心职责：
  - 渲染控制中心、模型管理、通讯账号、自动化任务、推送订阅、实时日志六个页面模块
  - 调用网关 API
  - 处理交互状态（编辑展开、详情查看、批量操作、敏感字段显示/隐藏）

### 1.2 后端网关

- 文件：`agent/services/gateway_server.py`
- 技术：FastAPI
- 核心职责：
  - 提供配置、自动化任务、运行历史、订阅、备份恢复 API
  - 校验输入并与项目存储层交互

### 1.3 推送适配层

- 文件：`core/automation/push_targets.py`
- 核心职责：
  - 将订阅参数转换为可发送目标
  - 发送通知（Apprise + Qmsg 直连分支）

---

## 2. 页面模块说明

## 2.1 控制中心（Dashboard）

### 功能

- 展示当前激活模型、通道、工作区信息
- 系统设置区支持：
  - 配置备份创建/刷新/查看/恢复/删除
  - 恢复默认配置
  - 默认配置文件查看
- Automation 全项目备份：
  - 备份创建/刷新/查看/恢复（merge/replace）/删除

### 前端关键状态

- `configBackups`
- `automationBackups`
- `defaultConfigFile`
- `defaultConfigContent`
- `showBackupViewer` / `backupViewerTitle` / `backupViewerContent`

### 前端关键函数

- 初始化：`init`
- 默认配置：`loadDefaultConfigInfo`、`viewDefaultConfig`
- 配置备份：`loadConfigBackups`、`createConfigBackup`、`viewConfigBackup`、`restoreConfigBackup`、`deleteConfigBackup`
- Automation 备份：`loadAutomationBackups`、`createAutomationBackup`、`viewAutomationBackup`、`restoreAutomationBackup`、`deleteAutomationBackup`
- 查看弹窗：`openBackupViewer`

### 对应后端 API

- `GET /api/config/default`
- `GET /api/config/backups`
- `GET /api/config/backups/{filename}`
- `POST /api/config/backup`
- `POST /api/config/restore`
- `DELETE /api/config/backups/{filename}`
- `POST /api/config/reset`
- `GET /api/automation/backups`
- `GET /api/automation/backups/{filename}`
- `POST /api/automation/backup`
- `POST /api/automation/restore`
- `DELETE /api/automation/backups/{filename}`

---

## 2.2 模型管理（Provider）

### 功能

- 模型实例增删改
- 设为激活模型
- 连接测试
- API Key 默认密码样式显示，支持眼睛图标切换明文

### 前端关键状态

- `config.provider.activeId`
- `config.provider.instances[]`
- `secretVisibility`（用于 API Key 显示/隐藏）

### 前端关键函数

- 数据标准化：`normalizeProviderInstance`
- 读取/切换激活：`getProviderInstances`、`getProviderActiveId`、`setProviderActiveId`、`isProviderActive`
- UI 操作：`addProviderInstance`、`removeProvider`、`getActiveProvider`
- 测试连接：`testProvider`

### 对应后端 API

- `POST /api/config/test-llm`
- `GET /api/config`
- `POST /api/config`

### 实现要点

- `testProvider` 会将前端 camelCase 字段映射为后端需要的 snake_case：
  - `modelName -> model_name`
  - `apiKey -> api_key`
  - `apiBase -> api_base`

---

## 2.3 通讯账号（Channel）

### 功能

- 按平台新增账号（Feishu/Telegram/QQ）
- 账号启停
- 设置活跃账号
- 单账号连通性验证
- 凭据字段默认隐藏，支持眼睛图标切换

### 前端关键状态

- `config.channel.activeId`
- `config.channel.accounts[]`
- `secretVisibility`

### 前端关键函数

- 标准化：`normalizeCredentials`、`normalizeChannelAccount`
- 账号集合：`getChannelAccounts`、`getChannelActiveId`、`setChannelActiveId`、`isChannelActive`
- UI 操作：`selectPlatform`、`removeChannel`、`getPlatformIcon`
- 连接测试：`testChannel`
- 敏感字段处理：`isSensitiveFieldKey`、`isSecretVisible`、`toggleSecretVisible`

### 对应后端 API

- `POST /api/config/test-im`
- `GET /api/config`
- `POST /api/config`

---

## 2.4 自动化任务（Automation）

### 功能

- 项目维度任务管理（查看/新增/编辑/删除/启停/冻结）
- 批量操作（运行、启停、冻结、删除）
- Cron 可视化（“定时规则”人类可读显示）
- Prompt 行内查看
- 编辑面板显示在当前任务行下方
- 运行历史与 Autoplan 最近运行：
  - 列表
  - 详情行内展开
  - 删除运行记录

### 前端关键状态

- `projects` / `selectedProjectId`
- `jobs`
- `showCreateJob`
- `editingJob`
- `viewingJobPromptId`
- `selectedJobIds`
- `runFilterJobId`
- `runs` / `autoplanRuns`
- `runDetail` / `runDetailAnchor`

### 前端关键函数（任务）

- 项目切换：`loadProjects`、`onProjectChange`
- 任务读取：`loadJobs`
- 新建：`resetNewJob`、`createJob`
- 编辑：`openEditJob`、`closeEditJob`、`saveEditJob`
- 执行与状态：`runJob`、`toggleJob`、`toggleFrozen`
- 删除：`deleteJob`
- 批量：`isSelected`、`toggleSelect`、`isAllSelected`、`toggleSelectAll`、`batchRunNow`、`batchSetEnabled`、`batchSetFrozen`、`batchDeleteJobs`
- Prompt 查看：`toggleViewJobPrompt`

### 前端关键函数（定时表达）

- `normalizeScheduleBuilder`
- `buildCronFromSchedule`
- `previewCron`
- `describeSchedule`
- `buildSchedulePayload`
- `parseTimeHHMM`、`toHHMM`

### 前端关键函数（运行记录）

- `loadRuns`
- `loadAutoplanRuns`
- `openRunDetail`
- `closeRunDetail`
- `deleteRun`

### 对应后端 API

- `GET /api/projects`
- `GET /api/projects/{pid}/jobs`
- `POST /api/projects/{pid}/jobs`
- `PUT /api/projects/{pid}/jobs/{job_id}`
- `DELETE /api/projects/{pid}/jobs/{job_id}`
- `POST /api/projects/{pid}/jobs/{job_id}/run`
- `GET /api/projects/{pid}/runs`
- `GET /api/projects/{pid}/runs/{run_id}`
- `DELETE /api/projects/{pid}/runs/{run_id}`

> 说明：`/api/projects/{pid}/bootstrap`、`/api/projects/{pid}/freeze-all-autoplan` 已在网关提供，但当前 `static/ui/index.html` 尚未挂接对应按钮。

---

## 2.5 推送订阅（Subscriptions）

### 功能

- 非邮件订阅（telegram/feishu/qq/wecombot/serverchan/custom）增删改查
- 非邮件订阅启停开关
- 单条测试 / 全部启用测试
- SMTP 邮件配置（快速模式）：
  - SMTP 配置增删改查
  - 预设服务商（QQ/163/Gmail/Outlook）
  - 启停、TLS 开关、默认配置切换、单配置测试发信
- 邮件订阅目标（`channel=email`）独立维护（收件人 + 可选 `profile_id`）
- 订阅指南（可折叠，内容在本节统一维护）
- 敏感字段隐藏与显示切换（含 token/key/smtp password）

### 前端关键状态

- `configSubscriptions`
- `editingConfigSubscriptionId`
- `configSubscriptionForm`
- `smtpProfiles` / `smtpPresets`
- `editingSmtpProfileId` / `smtpProfileForm`
- `editingEmailSubscriptionId` / `emailSubscriptionForm`
- `showSubscriptionGuide`
- `secretVisibility`

### 前端关键函数

- 订阅列表分组：`nonEmailConfigSubscriptions`、`emailConfigSubscriptions`
- 非邮件订阅表单：`resetConfigSubscriptionForm`、`startEditConfigSubscription`、`cancelEditConfigSubscription`
- 非邮件订阅数据：`loadConfigSubscriptions`、`saveConfigSubscription`、`deleteConfigSubscription`
- 非邮件订阅开关：`toggleConfigSubscription`
- 订阅测试：`testConfigSubscription`、`testAllEnabledConfigSubscriptions`
- SMTP 配置：`loadSmtpProfiles`、`applySmtpPreset`、`resetSmtpProfileForm`、`startEditSmtpProfile`、`cancelEditSmtpProfile`、`saveSmtpProfile`、`deleteSmtpProfile`、`toggleSmtpProfile`、`toggleSmtpTls`、`setDefaultSmtpProfile`、`testSmtpProfile`
- 邮件订阅：`resetEmailSubscriptionForm`、`startEditEmailSubscription`、`cancelEditEmailSubscription`、`saveEmailSubscription`、`testEmailSubscription`、`toggleEmailSubscription`、`deleteEmailSubscription`
- 展示：`formatSubscriptionTarget`
- Qmsg 预览：`qmsgEndpointPreview`

### 对应后端 API

- `GET /api/config/subscriptions`
- `GET /api/config/subscriptions/capabilities`
- `POST /api/config/subscriptions`
- `PUT /api/config/subscriptions/{subscription_id}`
- `DELETE /api/config/subscriptions/{subscription_id}`
- `POST /api/config/subscriptions/{subscription_id}/test`
- `POST /api/config/subscriptions/test-enabled`
- `GET /api/config/smtp-profiles`
- `POST /api/config/smtp-profiles`
- `PUT /api/config/smtp-profiles/{profile_id}`
- `DELETE /api/config/smtp-profiles/{profile_id}`
- `POST /api/config/smtp-profiles/{profile_id}/test`

### 推送发送路径（后端）

- 网关读取订阅 -> `build_apprise_url` -> `send_apprise_notification`
- 文件：`core/automation/push_targets.py`
- Qmsg 发送策略：
  - `send/group` => `application/x-www-form-urlencoded`
  - `jsend/jgroup` => `application/json`
- Email 发送策略：
  - `build_apprise_url(channel=email)` 生成 `email://recipient?profile_id=...`
  - `send_apprise_notification` 解析 `profile_id` 后，走 `_resolve_smtp_profile + _send_email_sync`

### 订阅数据结构（settings.json）

```json
{
  "id": "sub-1700000000000",
  "channel": "serverchan",
  "chat_id": "",
  "params": {
    "sendkey": "SCTxxxx"
  },
  "apprise_url": "",
  "enabled": true,
  "remark": "可选备注"
}
```

- `channel`: 渠道标识（telegram/feishu/qq/wecombot/serverchan/email/custom）
- `chat_id`: 兼容字段（可选）
- `params`: 按渠道配置参数
- `apprise_url`: 自定义完整 Apprise URL（`channel=custom` 常用）
- `enabled`: 是否启用
- `remark`: 备注

### 渠道字段说明（与 UI 折叠指南一致）

1. Telegram
- 必填：`params.bot_token`、`params.chat_id`
- URL：`tgram://{bot_token}/{chat_id}`
- 获取：`@BotFather` 创建机器人拿 token，`getUpdates` 获取 `chat.id`

2. Feishu（飞书自定义机器人）
- 必填：`params.token`
- URL：`feishu://{token}`
- 获取：Webhook 形如 `https://open.feishu.cn/open-apis/bot/v2/hook/<token>`

3. QQ Push（Qmsg）
- 必填：`params.token`
- 可选：`params.mode`（`send/group/jsend/jgroup`）、`params.qq`、`params.bot`
- URL：`qmsg://{mode}/{token}?qq=...&bot=...`
- 获取：`https://qmsg.zendee.cn/`，流程见 `https://qmsg.zendee.cn/docs/start/`

4. 微信（企业微信群机器人 / WeCom Bot）
- 必填：`params.key`
- URL：`wecombot://{key}`
- 获取：Webhook 形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>`

5. Server酱（方糖）
- 必填：`params.sendkey`
- URL：`schan://{sendkey}`
- 获取：`https://sct.ftqq.com/` 创建 SendKey

6. custom（自定义 Apprise URL）
- 必填：`apprise_url`
- 示例：`mailto://...`、`json://...`
- 参考：`https://appriseit.com/services/`

7. Email（SMTP 邮件）
- 必填：`params.email`
- 可选：`params.profile_id`
- URL：`email://{email}?profile_id={profile_id}`
- 使用：先配置 SMTP profile，再维护邮件订阅目标

### 订阅与 SMTP API 明细

1. 订阅 API
- `GET /api/config/subscriptions`
- `GET /api/config/subscriptions/capabilities`
- `POST /api/config/subscriptions`
- `PUT /api/config/subscriptions/{subscription_id}`
- `DELETE /api/config/subscriptions/{subscription_id}`
- `POST /api/config/subscriptions/{subscription_id}/test`
- `POST /api/config/subscriptions/test-enabled`

2. SMTP Profile API
- `GET /api/config/smtp-profiles`
- `POST /api/config/smtp-profiles`
- `PUT /api/config/smtp-profiles/{profile_id}`
- `DELETE /api/config/smtp-profiles/{profile_id}`
- `POST /api/config/smtp-profiles/{profile_id}/test`

### 与 settings.json 的关系

- 订阅 CRUD 接口每次变更都会写入 `settings.json` 的 `pushSubscriptions.items`。
- SMTP profile CRUD 接口每次变更都会写入 `settings.json` 的 `smtp.profiles`。
- `POST /api/config` 未显式带 `pushSubscriptions` 时，服务端保留现有订阅。
- `POST /api/config` 未显式带 `smtp` 时，服务端保留现有 SMTP 配置。

### 常见排查

- Server酱失败：检查 `params.sendkey`。
- QQ 失败：检查 `mode` 是否为 `send/group/jsend/jgroup`，以及 token 是否为空。
- Email 失败：检查 `params.email`、`params.profile_id` 指向 profile 是否存在且启用、默认 profile 是否可用。
- “测试”按钮语义：
  - 订阅行测试：`POST /api/config/subscriptions/{id}/test`
  - SMTP 行测试：`POST /api/config/smtp-profiles/{id}/test`
- 如果保存后订阅/SMTP 丢失，确认网关是否是最新代码版本。

---

## 2.6 实时日志（Logs）

### 功能

- WebSocket 实时输出后端日志
- 支持清空日志

### 前端关键状态

- `logs`

### 前端关键函数

- `initLogs`
- `showToast`

### 对应后端能力

- WebSocket：`/ws/logs`（日志流）

---

## 3. 通用函数与状态设计

### 3.1 配置标准化

- `normalizeConfig` 将服务端返回统一为前端可编辑结构。

### 3.2 统一时间/时长格式

- `formatTime`
- `formatDuration`

### 3.3 统一消息反馈

- `showToast(msg, type)`

### 3.4 敏感信息保护

- `secretVisibility` + `isSecretVisible` + `toggleSecretVisible`
- 适用于 Provider/Channel/Subscriptions 及 SMTP 密码字段。

---

## 4. 代码与函数定位清单

### 前端

- 页面与函数主体：`static/ui/index.html`
- `app()` 状态入口：约 `line 1150+`
- 自动化任务 UI：约 `line 305~695`
- 订阅 + SMTP + 邮件订阅 UI：约 `line 696~1148`
- 异步函数主区：约 `line 1426+`
- 自动化任务函数区：约 `line 1785+`
- 订阅与 SMTP 逻辑函数区：约 `line 1906~2380`

### 后端

- 网关 API：`agent/services/gateway_server.py`
- 配置/备份：约 `line 581~775`
- 订阅 + SMTP：约 `line 776~1065`
- 诊断：约 `line 1071~1209`
- 项目任务与运行：约 `line 1211~1506`

### 推送

- 目标构建与发送：`core/automation/push_targets.py`

---

## 5. 维护建议（面向后续开发）

1. 新增页面模块时，优先遵循“状态字段 + 函数组 + API 映射”结构。
2. 新增订阅渠道时，保持三处同步：
   - 前端表单 `configSubscriptionForm`
   - 网关能力声明 `/api/config/subscriptions/capabilities`
   - 发送层 `build_apprise_url`/`send_apprise_notification`
3. 若渠道为 Email，还需同步 SMTP 资料管理（profile CRUD / default / enabled）与订阅 `profile_id` 关联逻辑。
4. 对涉及密钥字段的 UI，一律按敏感字段规范（默认隐藏 + 可切换显示）。
5. 对任务调度显示，优先展示人类可读规则，原始 Cron 放 tooltip/详情。

---

## 6. 变更记录建议

建议后续将每次 UI 能力升级同步记录到：

- `README/guide/09_Web界面功能说明.md`（本文，单一事实来源）

以保持产品行为、代码实现、接口文档一致。
