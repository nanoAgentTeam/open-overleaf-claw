#!/usr/bin/env python3
"""
测试 RadarAutoplanService.reconcile_project() 能否正确：
1. 识别缺失的必要任务（T1-T5始终开启，T6/T7按条件开启）
2. 生成合规的任务 prompt（含 memory_nav/memory_write/notify_push 等）
3. 写入文件系统

用法：
  .venv/bin/python tests/scripts/test_autoplan.py
"""

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from providers.proxy import DynamicProviderProxy
from core.project import Project
from core.automation.store_fs import FSAutomationStore
from core.automation.models import AutomationJob, JobSchedule, OutputPolicy
from core.automation.radar_defaults import build_default_radar_jobs
from agent.radar_autopilot.autoplan import RadarAutoplanService

WORKSPACE = Path("workspace")

# ── 测试项目配置 ───────────────────────────────────────────────
TEST_PROJECT_ID = "test_autoplan_tmp"

RESEARCH_CORE = {
    "project_id": TEST_PROJECT_ID,
    "topic": "KV cache compression for LLM inference efficiency",
    "keywords": ["KV cache", "quantization", "LLM inference", "attention", "compression", "importance-guided"],
    "stage": "writing",
    "updated_at": "2026-03-01T10:00:00",
}

# 带 target_venue → 应触发 T6(conference.track) + T7(deadline.watch)
USER_PREFERENCE_WITH_VENUE = {
    "project_id": TEST_PROJECT_ID,
    "target_venue": "ICLR 2027",
    "deadline": "2026-10-01",
    "notify_channels": ["feishu"],
    "language": "zh",
}

# 无 target_venue → 仅需 T1-T5
USER_PREFERENCE_NO_VENUE = {
    "project_id": TEST_PROJECT_ID,
    "language": "zh",
}


def setup_test_project(with_venue: bool, initial_jobs: list[str] | None = None) -> Project:
    """
    创建临时测试项目，注入 research_core + user_preference profile，
    以及指定的初始任务（模拟"启动后已有部分任务"的状态）。
    """
    project_root = WORKSPACE / TEST_PROJECT_ID
    if project_root.exists():
        shutil.rmtree(project_root)
    project_root.mkdir(parents=True)

    mem_dir = project_root / ".project_memory"
    profiles_dir = mem_dir / "profiles"
    jobs_dir = mem_dir / "jobs"
    profiles_dir.mkdir(parents=True)
    jobs_dir.mkdir(parents=True)

    # 写入 research_core
    (profiles_dir / "research_core.current.json").write_text(
        json.dumps(RESEARCH_CORE, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写入 user_preference
    pref = USER_PREFERENCE_WITH_VENUE if with_venue else USER_PREFERENCE_NO_VENUE
    (profiles_dir / "user_preference.current.json").write_text(
        json.dumps(pref, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写入指定的初始任务（模拟"只有部分任务"）
    project = Project(TEST_PROJECT_ID, WORKSPACE)
    store = FSAutomationStore(project)

    if initial_jobs is None:
        # 默认：只有 radar.autoplan
        initial_jobs = ["radar.autoplan"]

    all_defaults = {j.id: j for j in build_default_radar_jobs()}

    for job_id in initial_jobs:
        if job_id == "radar.autoplan":
            job = AutomationJob(
                id="radar.autoplan",
                name="Radar Autoplan",
                type="normal",
                schedule=JobSchedule(cron="0 */12 * * *", timezone="Asia/Shanghai"),
                prompt="你是雷达任务自动编排器。判断是否需要新增/更新系统雷达任务。",
                enabled=True,
                managed_by="system",
                output_policy=OutputPolicy(mode="default"),
                metadata={"system_job": True, "origin": "system"},
            )
        elif job_id in all_defaults:
            job = all_defaults[job_id]
        else:
            print(f"  [WARN] 未知 initial_job: {job_id}")
            continue
        store.upsert_job(job)

    return project


def check_compliance(prompt: str, job_id: str) -> list[str]:
    """检查 prompt 是否满足合规要求 A-E，返回缺失项列表。"""
    checks = {
        "A (memory_nav)": "memory_nav" in prompt,
        "B (memory_list)": "memory_list" in prompt,
        "C (memory_write)": "memory_write" in prompt,
        "D (notify_push)": "notify_push" in prompt,
        "E (scope=job:)": f"job:{job_id}" in prompt or "job:radar." in prompt,
    }
    return [k for k, ok in checks.items() if not ok]


async def run_test(scenario_name: str, with_venue: bool, initial_jobs: list[str] | None = None):
    print(f"\n{'='*60}")
    print(f"场景: {scenario_name}")
    print(f"  with_venue={with_venue}, initial_jobs={initial_jobs}")
    print("="*60)

    project = setup_test_project(with_venue=with_venue, initial_jobs=initial_jobs)

    provider = DynamicProviderProxy()
    service = RadarAutoplanService(provider=provider, model=None)

    print("\n[1] 调用 reconcile_project()...")
    result = await service.reconcile_project(project)

    print(f"\n[2] 决策结果:")
    print(f"  decision : {result['decision']}")
    print(f"  reason   : {result['reason']}")
    applied = result.get("applied", {})
    print(f"  applied  : upserted={applied.get('upserted',0)}, disabled={applied.get('disabled',0)}, skipped={applied.get('skipped',0)}")

    print(f"\n[3] 现有任务列表:")
    store = FSAutomationStore(project)
    jobs = store.list_jobs()
    for j in sorted(jobs, key=lambda x: x.id):
        missing = check_compliance(j.prompt, j.id)
        compliance = "✅ 合规" if not missing else f"❌ 缺失: {missing}"
        print(f"  {'✓' if j.enabled else '✗'} {j.id:35s} {compliance}")

    # 验证预期
    print(f"\n[4] 验证:")
    job_ids = {j.id for j in jobs}
    always_on = ["radar.daily.scan", "radar.weekly.digest", "radar.urgent.alert",
                 "radar.direction.drift", "radar.profile.refresh"]
    for tid in always_on:
        ok = tid in job_ids
        print(f"  [{'OK' if ok else 'MISS'}] {tid} (始终开启)")

    conditional = {
        "radar.conference.track": with_venue,
        "radar.deadline.watch": with_venue,
    }
    for tid, should_exist in conditional.items():
        exists = tid in job_ids
        if should_exist:
            ok = exists
            print(f"  [{'OK' if ok else 'MISS'}] {tid} (条件开启, target_venue 有值)")
        else:
            ok = not exists
            print(f"  [{'OK' if ok else 'UNEXPECTED'}] {tid} (条件不满足, 不应存在)")

    # 清理
    shutil.rmtree(WORKSPACE / TEST_PROJECT_ID, ignore_errors=True)


async def main():
    print("AutoPlan 功能测试")
    print("模型:", "DynamicProviderProxy (step/stepfun)")

    # 场景一：项目只有 radar.autoplan，无 target_venue → 应创建 T1-T5
    await run_test(
        scenario_name="场景1: 全空项目，无目标会议",
        with_venue=False,
        initial_jobs=["radar.autoplan"],
    )

    # 场景二：项目有 radar.autoplan + 部分旧任务，有 target_venue → 应补全缺失任务
    await run_test(
        scenario_name="场景2: 有部分旧任务，有目标会议 ICLR 2027",
        with_venue=True,
        initial_jobs=["radar.autoplan", "radar.daily.scan", "radar.weekly.digest"],
    )

    # 场景三：全量任务已存在，有 target_venue → 应检查合规性，可能 no_change
    await run_test(
        scenario_name="场景3: 已有全量任务（包含新3个），有目标会议",
        with_venue=True,
        initial_jobs=["radar.autoplan", "radar.daily.scan", "radar.weekly.digest",
                      "radar.urgent.alert", "radar.direction.drift", "radar.profile.refresh",
                      "radar.conference.track", "radar.deadline.watch"],
    )


if __name__ == "__main__":
    asyncio.run(main())
