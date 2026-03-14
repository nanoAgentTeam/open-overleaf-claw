#!/usr/bin/env python3
"""
用真实项目测试 autoplan：
1. 复制 E2E_Test_W18 fixture（GNN论文）到临时项目
2. refresh_profiles() 从 tex 提取研究画像
3. bootstrap 默认定时任务（7个）
4. 运行 autoplan.reconcile_project()
5. 对比 before/after，展示 prompt 变化
"""
import asyncio
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from providers.proxy import DynamicProviderProxy
from core.project import Project
from core.automation.store_fs import FSAutomationStore
from core.automation.radar_defaults import build_default_radar_jobs
from core.memory.store import ProjectMemoryStore
from agent.radar_autopilot.autoplan import RadarAutoplanService

WORKSPACE = Path("workspace")
SRC_PROJECT = "E2E_Test_W18"
TMP_PROJECT = "test_autoplan_realworld"


def setup():
    """复制 fixture，初始化 profile + 默认任务。"""
    src = WORKSPACE / SRC_PROJECT / SRC_PROJECT
    dst_root = WORKSPACE / TMP_PROJECT
    dst = dst_root / TMP_PROJECT

    if dst_root.exists():
        shutil.rmtree(dst_root)
    shutil.copytree(src, dst)

    project = Project(TMP_PROJECT, WORKSPACE)

    # 1. 从 tex 文件提取研究画像
    print("[setup] 提取研究画像 (refresh_profiles)...")
    mem_store = ProjectMemoryStore(project)
    profiles = mem_store.refresh_profiles()
    rc = profiles.get("research_core", {})
    print(f"  topic   : {rc.get('topic', '(empty)')}")
    print(f"  keywords: {rc.get('keywords', [])}")
    print(f"  stage   : {rc.get('stage', '(empty)')}")

    # 2. 设置 user_preference（模拟有目标会议）
    up = {
        "project_id": TMP_PROJECT,
        "target_venue": "ICML 2026",
        "deadline": "2026-02-01",
        "notify_channels": ["feishu"],
        "language": "zh",
    }
    mem_store.write_profile("user_preference", up)
    print(f"  user_pref: target_venue={up['target_venue']}, deadline={up['deadline']}")

    # 3. bootstrap 默认定时任务
    store = FSAutomationStore(project)
    for job in build_default_radar_jobs():
        store.upsert_job(job)
    jobs = store.list_jobs()
    print(f"[setup] Bootstrap 完成，共 {len(jobs)} 个任务")

    return project


def show_prompt_diff(before: dict, after: dict):
    """比较 before/after 各任务 prompt 的差异。"""
    all_ids = sorted(set(before) | set(after))
    changed = []
    for jid in all_ids:
        old_p = before.get(jid, "")
        new_p = after.get(jid, "")
        if old_p != new_p:
            changed.append(jid)

    if not changed:
        print("  (无 prompt 变化)")
        return

    for jid in changed:
        old_p = before.get(jid, "(新增)")
        new_p = after.get(jid, "(删除)")
        print(f"\n  ── {jid} ─────────────────────────────────────")
        if old_p == "(新增)":
            print(f"  [NEW] prompt 长度: {len(new_p)} 字符")
            print(f"  前200字: {new_p[:200]}...")
        else:
            # 只展示长度变化 + 关键词差异
            print(f"  旧长度: {len(old_p)} | 新长度: {len(new_p)}")
            # 找 project-specific 词是否出现
            for kw in ["GraphAlign", "GNN", "graph", "contrastive", "ICML", "2026"]:
                was = kw.lower() in old_p.lower()
                now = kw.lower() in new_p.lower()
                if was != now:
                    marker = "新增↑" if now else "移除↓"
                    print(f"  [{marker}] 关键词 '{kw}'")


async def main():
    project = setup()
    store = FSAutomationStore(project)

    # 记录 before 状态
    before_jobs = {j.id: j.prompt for j in store.list_jobs()}
    print(f"\n[before] 共 {len(before_jobs)} 个任务")

    # 运行 autoplan
    print("\n[autoplan] 调用 reconcile_project()...")
    provider = DynamicProviderProxy()
    service = RadarAutoplanService(provider=provider, model=None)
    result = await service.reconcile_project(project)

    print(f"\n[result]")
    print(f"  decision : {result['decision']}")
    print(f"  reason   : {result['reason']}")
    applied = result.get("applied", {})
    print(f"  applied  : upserted={applied.get('upserted',0)}, disabled={applied.get('disabled',0)}, skipped={applied.get('skipped',0)}")

    # 记录 after 状态
    after_jobs = {j.id: j.prompt for j in store.list_jobs()}
    print(f"\n[after] 共 {len(after_jobs)} 个任务")

    # 展示 prompt 差异
    print("\n[prompt 变化分析]")
    show_prompt_diff(before_jobs, after_jobs)

    # 全量展示最终 prompt（摘要）
    print("\n\n" + "="*70)
    print("【最终各任务 prompt 摘要（前 300 字）】")
    print("="*70)
    for j in sorted(store.list_jobs(), key=lambda x: x.id):
        if j.id == "radar.autoplan":
            continue  # 跳过 autoplan 本身
        print(f"\n▶ {j.id} ({'✓' if j.enabled else '✗'})")
        print(j.prompt[:300])
        print("...")

    # 清理
    shutil.rmtree(WORKSPACE / TMP_PROJECT, ignore_errors=True)
    print("\n[done] 临时项目已清理。")


if __name__ == "__main__":
    asyncio.run(main())
