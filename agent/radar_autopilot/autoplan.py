"""Radar autoplan service: update system-managed radar jobs from project context."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from loguru import logger

from core.automation.models import (
    AutomationJob,
    OutputPolicy,
    SUPPORTED_JOB_TYPES,
)
from core.automation.store_fs import FSAutomationStore
from core.memory import ContextRenderer, ProjectMemoryStore


class RadarAutoplanService:
    """Generate and apply radar task updates from project content and interaction preference."""

    def __init__(self, provider: Any, model: str):
        self.provider = provider
        self.model = model

    async def reconcile_project(
        self,
        project: Any,
        *,
        actor_job_id: str | None = None,
        on_token: Any | None = None,
        agent_output: str | None = None,
    ) -> dict[str, Any]:
        store = FSAutomationStore(project)
        memory_store = ProjectMemoryStore(project)
        # Use read_profile (non-destructive) instead of refresh_profiles which overwrites existing JSON
        profiles = {
            "research_core": memory_store.read_profile("research_core"),
            "user_preference": memory_store.read_profile("user_preference"),
        }

        jobs = [j.to_dict() for j in store.list_jobs()]
        states = {j["id"]: store.get_job_state(j["id"]) for j in jobs if j.get("id")}
        recent_entries = memory_store.list_recent_entries(kind="", limit=20)
        context_block = ContextRenderer(memory_store).render_autoplan_context(
            jobs=jobs,
            states=states,
            recent_entries=recent_entries,
        )

        # Read autoplan config for permission control
        autoplan_cfg = None
        if project.config.automation:
            autoplan_cfg = project.config.automation.autoplan

        plan = await self.build_plan(
            project_id=project.id,
            profiles=profiles,
            jobs=jobs,
            states=states,
            recent_entries=recent_entries,
            context_block=context_block,
            on_token=on_token,
            agent_output=agent_output,
        )
        plan = self._normalize_plan(plan)
        applied = self.apply_plan(store, plan, autoplan_cfg=autoplan_cfg)

        return {
            "project_id": project.id,
            "decision": plan.get("decision", "no_change"),
            "reason": plan.get("reason", ""),
            "applied": applied,
            "at": datetime.now().isoformat(),
        }

    async def build_plan(
        self,
        project_id: str,
        profiles: dict[str, Any],
        jobs: list[dict[str, Any]],
        states: dict[str, Any],
        recent_entries: list[dict[str, Any]],
        context_block: str,
        on_token: Any | None = None,
        agent_output: str | None = None,
    ) -> dict[str, Any]:
        rc = profiles.get("research_core", {})
        up = profiles.get("user_preference", {})
        prompt = f"""
你是研究雷达自动编排器（autoplan）。你的职责是：确保项目中的定时任务套件完整、合规、贴合当前研究阶段。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【任务目录】—— autoplan 负责维护以下 7 类任务（按优先级）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【始终开启】
  T1. radar.daily.scan        每日 arXiv 增量扫描，检索新论文，评估相关度
  T2. radar.weekly.digest     每周一汇总日扫记录，生成可执行建议的周报
  T3. radar.urgent.alert      每4小时检测高优先级事件（竞争论文/外部冲击），达阈值推送
  T4. radar.direction.drift   每日检测研究方向漂移，提出任务调整建议
  T5. radar.profile.refresh   每日检测论文内容变化，自动刷新研究画像和关键词

【条件开启】
  T6. radar.conference.track  每周追踪主流会议录用结果，分析趋势，给出投稿建议
      激活条件：user_preference.target_venue 非空，或 research_core 涉及学术投稿场景
  T7. radar.deadline.watch    每日监控截稿日期，动态调整提醒级别（>30天→不推，7-30天→周推，≤7天→日推）
      激活条件：user_preference.deadline 非空，或 target_venue 非空（可通过搜索获取截稿日）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【Prompt 合规要求】—— 新建或更新任务时，生成的 prompt 必须包含：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  A. 历史读取：主路径靠系统注入的 rolling_summary + 近期运行记录，无需手动 memory_nav/list/get；
     prompt 中应说明「如需查更早详情，可用 memory_nav → memory_list → memory_get」作为备选路径
  B. 增量截点：扫描类任务（daily/urgent/conference）必须从 rolling_summary 中的上次执行时间推断 date_from
  C. 去重判断：基于 rolling_summary 中已记录的论文 ID / 事件 / 关键词进行去重，不对同一内容重复 notify_push
  D. 明确推送策略：区分任务类型——了解情况型（daily/weekly/conference/profile）有内容即推，预警型（urgent/drift）严格门槛只在真实威胁时推
  E. 记忆写入：执行记录由系统自动生成，禁止写 kind='job_run'；仅在有特殊发现需长期保留时才写 memory_write，
     kind 自定义（如 'paper_note'、'trend'、'snapshot'），scope='job:<task_id>'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【执行步骤】—— 按顺序完成以下三步分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1 — 合规性审查（针对现有任务）
  逐一检查 existing_jobs 中每个已启用任务的 prompt，判断是否满足合规要求 A-E。
  记录不合规任务的 ID 和缺失的合规项。

Step 2 — 完整性分析（基于项目画像）
  根据以下输入，判断缺少哪些必要任务：
  - T1-T5：始终应该存在且启用
  - T6 (conference.track)：target_venue={json.dumps(up.get("target_venue", ""), ensure_ascii=False)} → {"需要" if up.get("target_venue") else "暂不需要（target_venue 为空）"}
  - T7 (deadline.watch)：deadline={json.dumps(up.get("deadline", ""), ensure_ascii=False)}, target_venue={json.dumps(up.get("target_venue", ""), ensure_ascii=False)} → {"需要" if (up.get("deadline") or up.get("target_venue")) else "暂不需要（无目标会议和截稿日）"}

Step 3 — 最小操作输出
  对以下情况输出 operations：
  (a) 缺失的必要任务 → op=upsert，生成合规 prompt
  (b) prompt 不合规的现有任务 → op=upsert，补齐缺失的合规项（保留任务原有目标，仅补充缺失约束）
  (c) 不再满足激活条件的条件任务 → op=disable
  (d) Agent 建议的具体优化（如关键词细化、搜索策略调整）→ op=upsert，将建议融入现有 prompt（保留原有结构，仅增补建议内容）
  禁止对 frozen=true 的任务输出任何操作。
  若所有任务合规、完整、且无可执行的优化建议，输出 decision=no_change，operations=[]。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输入上下文】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

project_id: {project_id}
research_core: {json.dumps(rc, ensure_ascii=False)}
user_preference: {json.dumps(up, ensure_ascii=False)}
existing_jobs: {json.dumps(jobs, ensure_ascii=False)}
existing_job_states: {json.dumps(states, ensure_ascii=False)}
recent_job_run_entries（最近10条）: {json.dumps(recent_entries[:10], ensure_ascii=False)}

记忆上下文:
{context_block or "(empty)"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输出格式】—— 只输出 JSON，不要输出 Markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{
  "decision": "no_change|update",
  "reason": "简洁说明决策理由（合规审查结论 + 完整性分析结论）",
  "operations": [
    {{"op": "upsert", "job": {{
      "id": "radar.<task_name>",
      "name": "任务显示名",
      "type": "normal",
      "schedule": {{"cron": "<cron表达式>", "timezone": "<项目时区>"}},
      "prompt": "<满足合规要求A-E的完整prompt>",
      "enabled": true
    }}}},
    {{"op": "disable", "id": "radar.<task_name>"}}
  ]
}}
"""
        if agent_output:
            prompt += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【Autoplan Agent 执行建议】—— Agent 层的分析结论，必须作为 Step 3(d) 的输入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{agent_output}

处理规则：
- 如果 Agent 建议了具体的优化（如关键词细化、搜索范围调整、prompt 补充），你必须将其转化为 op=upsert 操作。
- upsert 时保留目标任务的原有 prompt 结构，仅在相关位置融入建议内容。
- 如果 Agent 输出的 decision 是 "no_new_tasks" 但包含 optimization_suggestions，这些 suggestions 仍应落地为 upsert。
- 如果 Agent 建议的内容在现有 prompt 中已覆盖，则跳过。
"""
        try:
            resp = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                tools=None,
                on_token=on_token,
            )
            raw = (resp.content or "").strip()
            plan = self._parse_json(raw)
            if not isinstance(plan, dict):
                return {"decision": "no_change", "reason": "invalid_json", "operations": []}
            return plan
        except Exception as e:
            logger.warning(f"Autoplan build failed: {e}")
            return {"decision": "no_change", "reason": f"error:{e}", "operations": []}

    def apply_plan(
        self,
        store: FSAutomationStore,
        plan: dict[str, Any],
        *,
        autoplan_cfg: Any | None = None,
    ) -> dict[str, Any]:
        ops = plan.get("operations", [])
        if not isinstance(ops, list):
            return {"upserted": 0, "disabled": 0, "skipped": 0}

        can_create = getattr(autoplan_cfg, "can_create", True) if autoplan_cfg else True
        max_system_jobs = getattr(autoplan_cfg, "max_system_jobs", 8) if autoplan_cfg else 8

        upserted = 0
        disabled = 0
        skipped = 0
        for op in ops:
            if not isinstance(op, dict):
                skipped += 1
                continue
            kind = str(op.get("op", "")).strip().lower()
            if kind == "upsert":
                raw_job = op.get("job")
                if not isinstance(raw_job, dict):
                    skipped += 1
                    continue
                try:
                    payload = self._build_job_payload(
                        store, raw_job,
                        can_create=can_create,
                        max_system_jobs=max_system_jobs,
                    )
                    if not payload:
                        skipped += 1
                        continue
                    job = AutomationJob.from_dict(payload)
                    store.upsert_job(job)
                    upserted += 1
                except Exception:
                    skipped += 1
            elif kind == "disable":
                job_id = str(op.get("id", "")).strip()
                if not job_id:
                    skipped += 1
                    continue
                existing = store.get_job(job_id)
                if not existing or existing.frozen:
                    skipped += 1
                    continue
                if store.disable_job(job_id):
                    disabled += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        return {"upserted": upserted, "disabled": disabled, "skipped": skipped}

    def _build_job_payload(
        self,
        store: FSAutomationStore,
        raw_job: dict[str, Any],
        *,
        can_create: bool = True,
        max_system_jobs: int = 8,
    ) -> dict[str, Any] | None:
        job_id = str(raw_job.get("id") or raw_job.get("job_id") or "").strip()
        if not job_id:
            return None

        existing = store.get_job(job_id)

        # Frozen jobs cannot be modified by autoplan
        if existing and existing.frozen:
            return None

        # New job creation: check can_create and max_system_jobs
        if not existing:
            if not can_create:
                return None
            system_count = sum(1 for j in store.list_jobs() if j.managed_by == "system")
            if system_count >= max_system_jobs:
                return None

        timezone_default = "UTC"
        if store.project.config.automation and store.project.config.automation.timezone:
            timezone_default = store.project.config.automation.timezone

        base = existing.to_dict() if existing else {}
        base_schedule = base.get("schedule", {}) if isinstance(base.get("schedule"), dict) else {}
        raw_schedule = raw_job.get("schedule", {})
        if isinstance(raw_schedule, str):
            raw_schedule = {"cron": raw_schedule, "timezone": timezone_default}
        if not isinstance(raw_schedule, dict):
            raw_schedule = {}

        cron = str(raw_schedule.get("cron") or base_schedule.get("cron") or "0 9 * * *").strip()
        timezone = str(
            raw_schedule.get("timezone")
            or base_schedule.get("timezone")
            or timezone_default
        ).strip()

        job_type = str(raw_job.get("type") or base.get("type") or "normal").strip().lower()
        if job_type not in SUPPORTED_JOB_TYPES:
            job_type = "normal"

        name = str(raw_job.get("name") or base.get("name") or job_id).strip() or job_id
        prompt = str(raw_job.get("prompt") or base.get("prompt") or "").strip()
        if not prompt:
            return None

        enabled_raw = raw_job.get("enabled")
        enabled = bool(base.get("enabled", True)) if enabled_raw is None else bool(enabled_raw)
        output_policy = raw_job.get("output_policy")
        if not isinstance(output_policy, dict):
            output_policy = base.get("output_policy") or OutputPolicy(mode="default").to_dict()

        metadata: dict[str, Any] = {}
        if isinstance(base.get("metadata"), dict):
            metadata.update(base.get("metadata"))
        if isinstance(raw_job.get("metadata"), dict):
            metadata.update(raw_job.get("metadata"))
        metadata["system_job"] = True
        if not existing:
            metadata["origin"] = "autoplan"

        return {
            "id": job_id,
            "name": name,
            "type": job_type,
            "schedule": {"cron": cron, "timezone": timezone or "UTC"},
            "prompt": prompt,
            "enabled": enabled,
            "managed_by": existing.managed_by if existing else "system",
            "frozen": False,
            "output_policy": output_policy,
            "metadata": metadata,
        }

    def _normalize_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict):
            return {"decision": "no_change", "reason": "invalid_plan", "operations": []}

        decision = str(plan.get("decision", "")).strip().lower()
        raw_ops = plan.get("operations", [])
        if not isinstance(raw_ops, list):
            raw_ops = []

        jobs = plan.get("jobs", [])
        if isinstance(jobs, list):
            for item in jobs:
                if isinstance(item, dict):
                    raw_ops.append({"op": "upsert", "job": item})
        disable_ids = plan.get("disable_ids", [])
        if isinstance(disable_ids, list):
            for item in disable_ids:
                jid = str(item).strip()
                if jid:
                    raw_ops.append({"op": "disable", "id": jid})

        normalized_ops: list[dict[str, Any]] = []
        for op in raw_ops:
            if not isinstance(op, dict):
                continue
            kind = str(op.get("op", "")).strip().lower()
            if kind in {"upsert", "create", "update"}:
                job = op.get("job")
                if isinstance(job, dict):
                    normalized_ops.append({"op": "upsert", "job": job})
            elif kind in {"disable", "off", "delete"}:
                jid = str(op.get("id", "")).strip()
                if jid:
                    normalized_ops.append({"op": "disable", "id": jid})

        if decision not in {"no_change", "update"}:
            decision = "update" if normalized_ops else "no_change"

        reason = str(plan.get("reason", "")).strip()
        notes = str(plan.get("notes", "")).strip()
        payload = {
            "decision": decision,
            "reason": reason or ("ops_present" if normalized_ops else "no_ops"),
            "operations": normalized_ops,
        }
        if notes:
            payload["notes"] = notes
        return payload

    @staticmethod
    def _parse_json(raw: str) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
