#!/usr/bin/env python3
"""Assert memory/job_state artifacts after radar replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEPRECATED_STATE_KEYS = {"last_note_ref", "last_run_id", "last_error", "last_trigger"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file (one JSON object per line)."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _assert(condition: bool, message: str, errors: list[str]) -> None:
    if condition:
        print(f"[ok] {message}")
    else:
        print(f"[fail] {message}")
        errors.append(message)


def _build_id_map(index_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in index_rows:
        if not isinstance(row, dict):
            continue
        mem_id = str(row.get("id", "")).strip()
        if mem_id:
            out[mem_id] = row
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert memory artifacts for radar unification.")
    parser.add_argument("--project-id", default="multi-agent-project")
    parser.add_argument(
        "--replay-report",
        default="",
        help="Optional replay report json from radar_command_replay.py",
    )
    parser.add_argument(
        "--expect-min-new-job-runs",
        type=int,
        default=2,
        help="Minimum number of new job_run entries expected from replay report.",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    memory_root = repo_root / "workspace" / args.project_id / ".project_memory"
    index_path = memory_root / "index.jsonl"
    state_daily_path = memory_root / "job_states" / "radar.daily.scan.json"
    state_autoplan_path = memory_root / "job_states" / "radar.autoplan.json"

    errors: list[str] = []

    index_rows = _load_jsonl(index_path)
    _assert(isinstance(index_rows, list), "index.jsonl is a list", errors)
    index_rows = index_rows if isinstance(index_rows, list) else []
    id_map = _build_id_map(index_rows)

    state_daily = _load_json(state_daily_path, {})
    state_autoplan = _load_json(state_autoplan_path, {})
    _assert(isinstance(state_daily, dict), "daily job state json is valid", errors)
    _assert(isinstance(state_autoplan, dict), "autoplan job state json is valid", errors)
    state_daily = state_daily if isinstance(state_daily, dict) else {}
    state_autoplan = state_autoplan if isinstance(state_autoplan, dict) else {}

    for label, state in (("daily", state_daily), ("autoplan", state_autoplan)):
        _assert("last_entry_id" in state, f"{label} state has last_entry_id", errors)
        _assert("run_count" in state, f"{label} state has run_count", errors)
        _assert("consecutive_failures" in state, f"{label} state has consecutive_failures", errors)
        for deprecated in DEPRECATED_STATE_KEYS:
            _assert(deprecated not in state, f"{label} state removed deprecated key: {deprecated}", errors)

        mem_id = str(state.get("last_entry_id", "")).strip()
        _assert(bool(mem_id), f"{label} state last_entry_id is non-empty", errors)
        row = id_map.get(mem_id)
        _assert(row is not None, f"{label} state last_entry_id exists in index", errors)
        if row is not None:
            _assert(str(row.get("kind", "")).strip() == "job_run", f"{label} last entry kind=job_run", errors)
            expected_scope = "job:radar.daily.scan" if label == "daily" else "job:radar.autoplan"
            _assert(str(row.get("scope", "")).strip() == expected_scope, f"{label} last entry scope matches", errors)

    if args.replay_report:
        report_path = Path(args.replay_report).expanduser().resolve()
        report = _load_json(report_path, {})
        _assert(isinstance(report, dict), "replay report is valid json object", errors)
        report = report if isinstance(report, dict) else {}

        commands = report.get("commands", [])
        _assert(isinstance(commands, list), "replay report has commands list", errors)
        commands = commands if isinstance(commands, list) else []
        for item in commands:
            cmd = str(item.get("command", "")).strip()
            response = str(item.get("response", "")).strip()
            _assert(bool(cmd), "replay command label exists", errors)
            _assert("[ERROR]" not in response and "Command failed:" not in response, f"{cmd} has no command error", errors)

        pre = report.get("pre", {})
        post = report.get("post", {})
        pre_daily_count = _to_int((pre if isinstance(pre, dict) else {}).get("state_daily", {}).get("run_count"))
        pre_autoplan_count = _to_int((pre if isinstance(pre, dict) else {}).get("state_autoplan", {}).get("run_count"))
        post_daily_count = _to_int((post if isinstance(post, dict) else {}).get("state_daily", {}).get("run_count"))
        post_autoplan_count = _to_int((post if isinstance(post, dict) else {}).get("state_autoplan", {}).get("run_count"))
        _assert(post_daily_count >= pre_daily_count + 1, "daily run_count incremented by at least 1", errors)
        _assert(post_autoplan_count >= pre_autoplan_count + 1, "autoplan run_count incremented by at least 1", errors)

        new_ids = report.get("new_entry_ids", [])
        _assert(isinstance(new_ids, list), "replay report new_entry_ids is list", errors)
        new_ids = [str(i).strip() for i in (new_ids if isinstance(new_ids, list) else []) if str(i).strip()]
        _assert(len(new_ids) >= args.expect_min_new_job_runs, "new job_run entries meet minimum delta", errors)
        for mem_id in new_ids:
            row = id_map.get(mem_id)
            _assert(row is not None, f"new entry {mem_id} exists in index", errors)
            if row is not None:
                _assert(str(row.get("kind", "")).strip() == "job_run", f"new entry {mem_id} kind=job_run", errors)

    if errors:
        print(f"[result] FAILED ({len(errors)} checks failed)")
        return 1
    print("[result] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

