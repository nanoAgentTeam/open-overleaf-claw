#!/usr/bin/env python3
"""Replay radar commands through the same command-handler path used by the app."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workspace_root(repo_root: Path) -> Path:
    return repo_root / "workspace"


def _project_memory_root(workspace_root: Path, project_id: str) -> Path:
    return workspace_root / project_id / ".project_memory"


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


def _snapshot(memory_root: Path) -> dict[str, Any]:
    index = _load_jsonl(memory_root / "index.jsonl")
    index_ids = [str(row.get("id", "")).strip() for row in index if isinstance(row, dict)]
    states_dir = memory_root / "job_states"
    daily = _load_json(states_dir / "radar.daily.scan.json", {})
    autoplan = _load_json(states_dir / "radar.autoplan.json", {})
    return {
        "index_count": len(index_ids),
        "index_ids": index_ids,
        "state_daily": daily if isinstance(daily, dict) else {},
        "state_autoplan": autoplan if isinstance(autoplan, dict) else {},
    }


class MockProvider:
    api_key = "test"
    api_base = "test"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_token: Any | None = None,
    ) -> Any:
        from providers.base import LLMResponse

        text = "mock-execution-ok"
        if on_token:
            try:
                on_token(text)
            except Exception:
                pass
        return LLMResponse(content=text, tool_calls=[], finish_reason="stop", usage={})

    def get_default_model(self) -> str:
        return "mock"


class _Services:
    pass


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root()
    workspace_root = _workspace_root(repo_root)
    memory_root = _project_memory_root(workspace_root, args.project_id)

    if args.safe_cwd:
        os.chdir("/tmp")

    sys.path.insert(0, str(repo_root))

    from agent.services.commands import RadarHandler
    from agent.services.protocols import CommandContext
    from config.loader import load_config
    from core.project import Project

    pre = _snapshot(memory_root)

    project = Project(args.project_id, workspace_root)
    services = _Services()
    services._project = project
    services.provider = MockProvider()
    services.model = "mock-model"
    services.workspace = workspace_root
    services.config = load_config()
    services.brave_api_key = None
    services.s2_api_key = None

    handler = RadarHandler()
    handler.bind(services)
    ctx = CommandContext(
        chat_id=args.chat_id,
        channel=args.channel,
        sender_id="user",
        mode="NORMAL",
        project_id=args.project_id,
        session_id="automation",
        role_name="Assistant",
        role_type="Assistant",
    )

    steps = [
        ("/radar status", "status"),
        ("/radar run radar.daily.scan", "run radar.daily.scan"),
        ("/radar autoplan run", "autoplan run"),
    ]

    commands: list[dict[str, Any]] = []
    for label, raw_args in steps:
        result = await handler.execute(raw_args, ctx)
        commands.append(
            {
                "command": label,
                "args": raw_args,
                "response": result.response,
                "should_continue": bool(result.should_continue),
            }
        )

    post = _snapshot(memory_root)
    pre_ids = set(pre.get("index_ids", []))
    post_ids = set(post.get("index_ids", []))
    new_ids = sorted(i for i in post_ids if i and i not in pre_ids)

    report = {
        "project_id": args.project_id,
        "safe_cwd": bool(args.safe_cwd),
        "commands": commands,
        "pre": pre,
        "post": post,
        "new_entry_ids": new_ids,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay radar command flow and capture artifact deltas.")
    parser.add_argument("--project-id", default="multi-agent-project")
    parser.add_argument("--chat-id", default="tests-radar-replay")
    parser.add_argument("--channel", default="cli")
    parser.add_argument(
        "--safe-cwd",
        action="store_true",
        help="Switch cwd to /tmp before replay to avoid local GUI/tooling side effects.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output json path (default prints to stdout only).",
    )
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"[replay] wrote report: {out_path}")
    print(payload)

    errors = []
    for item in report.get("commands", []):
        response = str(item.get("response") or "")
        if "[ERROR]" in response or "Command failed:" in response:
            errors.append(f"command failed: {item.get('command')}")
    if errors:
        for msg in errors:
            print(f"[replay][error] {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

