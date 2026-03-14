#!/usr/bin/env python3
"""Assert autoplan control-plane behavior for frozen/can_create/max_system_jobs."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _assert(condition: bool, message: str, errors: list[str]) -> None:
    if condition:
        print(f"[ok] {message}")
    else:
        print(f"[fail] {message}")
        errors.append(message)


def _project_payload(project_id: str, *, can_create: bool, max_system_jobs: int) -> dict[str, Any]:
    return {
        "name": project_id,
        "git": {
            "enabled": False,
            "auto_commit": False,
            "auto_pull": False,
            "commit_prefix": "[bot]",
        },
        "automation": {
            "enabled": True,
            "timezone": "UTC",
            "autoplan": {
                "enabled": True,
                "schedule": "0 */12 * * *",
                "run_on_sync_pull": True,
                "can_create": can_create,
                "max_system_jobs": max_system_jobs,
            },
        },
    }


def _create_project(workspace: Path, project_id: str, *, can_create: bool, max_system_jobs: int) -> Any:
    root = workspace / project_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        yaml.dump(_project_payload(project_id, can_create=can_create, max_system_jobs=max_system_jobs), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    from core.project import Project

    return Project(project_id, workspace)


def _seed_job(
    store: Any,
    *,
    job_id: str,
    prompt: str,
    enabled: bool = True,
    managed_by: str = "system",
    frozen: bool = False,
    origin: str = "system",
) -> None:
    from core.automation.models import AutomationJob, JobSchedule, OutputPolicy

    store.upsert_job(
        AutomationJob(
            id=job_id,
            name=job_id,
            type="normal",
            schedule=JobSchedule(cron="0 9 * * *", timezone="UTC"),
            prompt=prompt,
            enabled=enabled,
            managed_by=managed_by,
            frozen=frozen,
            output_policy=OutputPolicy(mode="default"),
            metadata={"system_job": True, "origin": origin},
        )
    )


def _upsert_plan(job_id: str, prompt: str) -> dict[str, Any]:
    return {
        "decision": "update",
        "operations": [
            {
                "op": "upsert",
                "job": {
                    "id": job_id,
                    "name": job_id,
                    "type": "normal",
                    "schedule": {"cron": "15 10 * * *", "timezone": "UTC"},
                    "prompt": prompt,
                    "enabled": True,
                },
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert autoplan control behavior.")
    parser.add_argument("--workspace-root", default="", help="Optional workspace root for debug; default creates temp dir.")
    args = parser.parse_args()

    repo_root = _repo_root()
    import sys

    sys.path.insert(0, str(repo_root))
    from core.automation.store_fs import FSAutomationStore
    from agent.radar_autopilot import RadarAutoplanService

    temp_workspace: tempfile.TemporaryDirectory[str] | None = None
    if args.workspace_root:
        workspace = Path(args.workspace_root).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
    else:
        temp_workspace = tempfile.TemporaryDirectory(prefix="autoplan-controls-")
        workspace = Path(temp_workspace.name)

    errors: list[str] = []
    service = RadarAutoplanService(provider=None, model="mock")

    # 1) Config round-trip must persist can_create/max_system_jobs.
    p_cfg = _create_project(workspace, "p_cfg", can_create=False, max_system_jobs=3)
    p_cfg.save_config()
    saved_cfg = yaml.safe_load((workspace / "p_cfg" / "project.yaml").read_text(encoding="utf-8")) or {}
    saved_autoplan = ((saved_cfg.get("automation") or {}).get("autoplan") or {})
    _assert(saved_autoplan.get("can_create") is False, "save_config persists autoplan.can_create", errors)
    _assert(int(saved_autoplan.get("max_system_jobs", -1)) == 3, "save_config persists autoplan.max_system_jobs", errors)

    # 2) can_create=false blocks creation.
    p_no_create = _create_project(workspace, "p_no_create", can_create=False, max_system_jobs=8)
    store_no_create = FSAutomationStore(p_no_create)
    res_no_create = service.apply_plan(
        store_no_create,
        _upsert_plan("radar.new.blocked", "blocked by can_create=false"),
        autoplan_cfg=p_no_create.config.automation.autoplan,
    )
    _assert(res_no_create.get("upserted") == 0, "can_create=false results in no upsert", errors)
    _assert(store_no_create.get_job("radar.new.blocked") is None, "can_create=false does not create job file", errors)

    # 3) max_system_jobs caps new system jobs.
    p_max = _create_project(workspace, "p_max", can_create=True, max_system_jobs=1)
    store_max = FSAutomationStore(p_max)
    _seed_job(store_max, job_id="radar.seed", prompt="seed")
    res_max = service.apply_plan(
        store_max,
        _upsert_plan("radar.new.maxed", "blocked by max_system_jobs"),
        autoplan_cfg=p_max.config.automation.autoplan,
    )
    _assert(res_max.get("upserted") == 0, "max_system_jobs reached results in no upsert", errors)
    _assert(store_max.get_job("radar.new.maxed") is None, "max_system_jobs reached does not create job file", errors)

    # 4) frozen jobs cannot be updated/disabled by autoplan.
    p_frozen = _create_project(workspace, "p_frozen", can_create=True, max_system_jobs=8)
    store_frozen = FSAutomationStore(p_frozen)
    _seed_job(
        store_frozen,
        job_id="radar.keep",
        prompt="original frozen prompt",
        enabled=True,
        managed_by="user",
        frozen=True,
        origin="user",
    )
    res_frozen = service.apply_plan(
        store_frozen,
        {
            "decision": "update",
            "operations": [
                {
                    "op": "upsert",
                    "job": {
                        "id": "radar.keep",
                        "prompt": "autoplan should not overwrite this",
                        "schedule": {"cron": "0 6 * * *", "timezone": "UTC"},
                    },
                },
                {"op": "disable", "id": "radar.keep"},
            ],
        },
        autoplan_cfg=p_frozen.config.automation.autoplan,
    )
    kept = store_frozen.get_job("radar.keep")
    _assert(res_frozen.get("upserted") == 0 and res_frozen.get("disabled") == 0, "frozen job ops are skipped", errors)
    _assert(kept is not None and kept.prompt == "original frozen prompt", "frozen job prompt remains unchanged", errors)
    _assert(kept is not None and kept.enabled is True and kept.frozen is True, "frozen job remains enabled+frozen", errors)

    # 5) Autoplan-created jobs are tagged with origin and unfrozen.
    p_create = _create_project(workspace, "p_create", can_create=True, max_system_jobs=8)
    store_create = FSAutomationStore(p_create)
    res_create = service.apply_plan(
        store_create,
        _upsert_plan("radar.created", "created by autoplan"),
        autoplan_cfg=p_create.config.automation.autoplan,
    )
    created = store_create.get_job("radar.created")
    _assert(res_create.get("upserted") == 1, "autoplan can create when policy allows", errors)
    _assert(created is not None and created.managed_by == "system", "autoplan-created job managed_by=system", errors)
    _assert(created is not None and created.frozen is False, "autoplan-created job frozen=false", errors)
    _assert((created.metadata or {}).get("origin") == "autoplan", "autoplan-created job metadata.origin=autoplan", errors)

    if temp_workspace is not None:
        temp_workspace.cleanup()

    if errors:
        print(f"[result] FAILED ({len(errors)} checks failed)")
        return 1
    print("[result] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
