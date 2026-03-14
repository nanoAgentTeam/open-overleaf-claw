#!/usr/bin/env python3
"""Assert automation-session tool registry excludes legacy memory tools."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_isolated_tool_config(repo_root: Path) -> Path:
    src = repo_root / "config" / "tools.json"
    rows = json.loads(src.read_text(encoding="utf-8"))
    wanted = {
        "save_memory",
        "retrieve_memory",
        "memory_get",
        "memory_search",
        "memory_nav",
        "memory_list",
        "memory_write",
        "memory_brief",
        "profile_read",
        "profile_refresh",
    }
    filtered = [row for row in rows if str(row.get("name", "")).strip() in wanted]

    temp_root = Path(tempfile.mkdtemp(prefix="radar-tools-"))
    cfg_dir = temp_root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "tools.json").write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return temp_root


class MockProvider:
    api_key = "test"
    api_base = "test"

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        from providers.base import LLMResponse

        return LLMResponse(content="ok", tool_calls=[], finish_reason="stop", usage={})

    def get_default_model(self) -> str:
        return "mock"


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert automation-session tool registry behavior.")
    parser.add_argument("--project-id", default="multi-agent-project")
    parser.add_argument(
        "--isolate-tools",
        action="store_true",
        help="Use a temporary filtered tools.json to avoid unrelated heavy tool imports.",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    if args.isolate_tools:
        os.chdir(_build_isolated_tool_config(repo_root))
    sys.path.insert(0, str(repo_root))

    from bus.queue import MessageBus
    from config.loader import load_config
    from core.project import Project
    from agent.loop import AgentLoop

    workspace = repo_root / "workspace"
    project = Project(args.project_id, workspace)
    session = project.session("automation", role_type="Assistant")

    loop = AgentLoop(
        bus=MessageBus(),
        provider=MockProvider(),
        workspace=workspace,
        model="mock-model",
        project_id=project.id,
        session_id=session.id,
        mode="NORMAL",
        role_name="Assistant",
        profile="automation_agent",
        config=load_config(),
        project=project,
        session=session,
    )

    names = sorted(defn["function"]["name"] for defn in loop.tools.get_definitions())
    print(json.dumps({"tool_count": len(names), "tools": names}, ensure_ascii=False, indent=2))

    errors: list[str] = []
    if "save_memory" in names:
        errors.append("save_memory should not be registered in automation session")
    if "retrieve_memory" in names:
        errors.append("retrieve_memory should not be registered in automation session")
    for required in ("memory_nav", "memory_list", "memory_get", "memory_write"):
        if required not in names:
            errors.append(f"{required} should be registered in automation session")

    if errors:
        for msg in errors:
            print(f"[fail] {msg}")
        print(f"[result] FAILED ({len(errors)} checks failed)")
        return 1
    print("[result] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
