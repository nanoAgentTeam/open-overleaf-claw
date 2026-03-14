# Harness: Memory/Radar Checks

This folder contains lightweight executable checks for memory/radar unification.

## Scripts

- `radar_command_replay.py`
  - Replays:
    1. `/radar status`
    2. `/radar run radar.daily.scan`
    3. `/radar autoplan run`
  - Captures pre/post snapshots and new memory entry IDs.

- `assert_memory_artifacts.py`
  - Validates memory index/job_state structure and replay deltas.

- `assert_tool_registry.py`
  - Validates automation-session tool registry excludes legacy memory tools.
  - Uses `--isolate-tools` mode to load a filtered temporary `tools.json` through the same loader path.

- `assert_autoplan_controls.py`
  - Validates autoplan control-plane behavior:
    1. `frozen` blocks autoplan update/disable.
    2. `can_create` gates autoplan create.
    3. `max_system_jobs` limits system-job creation.
    4. `project.save_config()` persists `autoplan.can_create/max_system_jobs`.

- `run_memory_radar_checks.sh`
  - One-shot runner for all checks.

## Quick Start

```bash
cd /Users/zc/PycharmProjects/open-overleaf-claw
bash tests/harness/run_memory_radar_checks.sh
```

## Environment knobs

- `PYTHON_BIN` (default: `.venv/bin/python`)
- `PROJECT_ID` (default: `multi-agent-project`)
- `SAFE_CWD` (default: `1`)
  - `1`: switch cwd to `/tmp` for replay/registry checks to avoid local GUI/tool side effects.
  - `0`: keep current cwd.
