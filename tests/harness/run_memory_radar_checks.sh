#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
PROJECT_ID="${PROJECT_ID:-multi-agent-project}"
SAFE_CWD="${SAFE_CWD:-1}"

REPORT_DIR="$ROOT_DIR/tests/harness/out"
REPORT_PATH="$REPORT_DIR/radar_replay_report.json"
mkdir -p "$REPORT_DIR"

echo "[run] python: $PYTHON_BIN"
echo "[run] project: $PROJECT_ID"

SAFE_FLAG=""
if [[ "$SAFE_CWD" == "1" ]]; then
  SAFE_FLAG="--safe-cwd"
fi

set -x
"$PYTHON_BIN" "$ROOT_DIR/tests/harness/radar_command_replay.py" \
  --project-id "$PROJECT_ID" \
  $SAFE_FLAG \
  --output "$REPORT_PATH"

"$PYTHON_BIN" "$ROOT_DIR/tests/harness/assert_memory_artifacts.py" \
  --project-id "$PROJECT_ID" \
  --replay-report "$REPORT_PATH"

"$PYTHON_BIN" "$ROOT_DIR/tests/harness/assert_tool_registry.py" \
  --project-id "$PROJECT_ID" \
  --isolate-tools

"$PYTHON_BIN" "$ROOT_DIR/tests/harness/assert_autoplan_controls.py"
set +x

echo "[done] all checks passed"
echo "[done] replay report: $REPORT_PATH"
