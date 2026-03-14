import os
import sys
import json
import shutil
import signal
import tempfile
import yaml
import asyncio
from pathlib import Path
from datetime import datetime


class SnapshotManager:
    """
    Snapshot the fixture directory before a test run, then after the run:
      1. Move the entire modified project dir to the archive.
      2. Restore the original fixture from the snapshot.

    Archive layout:
        tests/runs/{timestamp}/{project_id}/
            run_result.json
            stdout.txt          (omitted on timeout)
            workspace/          <- moved from workspace/{project_id}/
                project.yaml
                {project_id}/   <- modified fixture (what the agent changed)
                {session_id}/   <- session dir with trace & artifacts
    """

    def __init__(self, workspace_root: Path, runs_root: Path, project_id: str,
                 batch_timestamp: str | None = None):
        self.workspace_root = workspace_root
        self.runs_root = runs_root
        self.project_id = project_id
        self.project_dir = workspace_root / project_id
        self.fixture_dir = self.project_dir / project_id   # core directory
        self._snapshot_tmp: Path | None = None
        # Use a shared batch timestamp so all cases in the same run share one directory
        self._batch_timestamp = batch_timestamp

    def snapshot(self):
        """Deep-copy the fixture to a temp dir before the test modifies anything."""
        if not self.fixture_dir.exists():
            print(f"[Snapshot] Warning: fixture dir not found, nothing to snapshot: {self.fixture_dir}")
            return

        tmp = Path(tempfile.mkdtemp(prefix=f"e2e_{self.project_id}_"))
        shutil.copytree(str(self.fixture_dir), str(tmp / self.project_id))
        self._snapshot_tmp = tmp
        print(f"[Snapshot] Fixture captured → {tmp}")

    def archive_and_restore(self, run_result: dict, stdout: str) -> Path:
        """
        Move the modified workspace to the archive dir, save metadata,
        then restore the original fixture from the snapshot.
        Returns the archive dir path.
        """
        timestamp = self._batch_timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = self.runs_root / timestamp / self.project_id
        archive_dir.mkdir(parents=True, exist_ok=True)

        # 1. Move modified project workspace into the archive
        if self.project_dir.exists():
            shutil.move(str(self.project_dir), str(archive_dir / "workspace"))
            print(f"[Archive] Workspace moved → {archive_dir / 'workspace'}")
        else:
            print(f"[Archive] Warning: project dir not found, nothing to archive.")

        # 2. Save run_result.json and stdout.txt alongside the workspace
        (archive_dir / "run_result.json").write_text(
            json.dumps(run_result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if stdout and stdout != "[TIMEOUT]":
            (archive_dir / "stdout.txt").write_text(stdout, encoding="utf-8")

        print(f"[Archive] Run artifacts saved → {archive_dir}")

        # 3. Restore: recreate project_dir, then copy fixture from snapshot
        self.project_dir.mkdir(parents=True, exist_ok=True)

        if self._snapshot_tmp is not None:
            snapshot_fixture = self._snapshot_tmp / self.project_id
            if snapshot_fixture.exists():
                shutil.copytree(str(snapshot_fixture), str(self.fixture_dir))
                shutil.rmtree(str(self._snapshot_tmp))
                self._snapshot_tmp = None
                print(f"[Restore] Workspace restored to pre-test state.")
            else:
                print(f"[Restore] Warning: snapshot content missing, workspace not restored.")
        else:
            print(f"[Restore] Warning: no snapshot was taken, workspace not restored.")

        return archive_dir


class TestEnvironment:
    """Setup and teardown the Test Environment for the external runner."""

    def __init__(self, workspace_root: Path, case_config: dict):
        self.workspace_root = workspace_root
        self.config = case_config
        self.project_id = self.config.get('project_id', 'E2E_TestProject')
        self.session_id = datetime.now().strftime("%m%d_E2E")
        self.project_path = self.workspace_root / self.project_id

    def setup(self):
        """Prepare the directory, project.yaml and link Overleaf ID"""
        print(f"[Setup] Initializing test project: {self.project_id}")
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Write project.yaml
        overleaf_id = self.config.get('overleaf_id', '')

        project_yaml = {
            "name": self.project_id,
            "strategy": "interactive",
            "main_tex": self.config.get('main_tex', 'main.tex'),
            "git": {
                "enabled": True,
                "auto_commit": True,
                "auto_pull": True,
                "commit_prefix": "[bot]"
            },
            "overleaf": {
                "project_id": overleaf_id,
                "auto_pull_before_work": True,
                "sync_interval_hours": 0
            }
        }

        yaml_path = self.project_path / "project.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(project_yaml, f, allow_unicode=True)

        # If the fixture (core) dir has a pre-embedded .project_memory/,
        # copy it up to the project_dir level where ProjectKnowledgeStore reads from.
        # (project.root = project_dir, project.core = fixture_dir)
        fixture_memory = self.project_path / self.project_id / ".project_memory"
        project_memory = self.project_path / ".project_memory"
        if fixture_memory.exists() and not project_memory.exists():
            shutil.copytree(str(fixture_memory), str(project_memory))
            print(f"[Setup] Pre-embedded memory copied to project level: {project_memory}")

        return self.project_id, self.session_id


class E2ERunner:
    """External runner for triggering ContextBot."""

    def __init__(self, cli_path: Path):
        self.cli_path = cli_path

    async def run_case(self, project_id: str, session_id: str, query: str,
                       timeout_sec: int = 300, mode: str = "NORMAL") -> tuple[str, int]:
        """Spawn the ContextBot agent subprocess and inject the query."""

        # For TASK mode: wrap query with /task prefix; --e2e on CLI auto-injects --e2e into /task
        effective_query = f"/task {query}" if mode.upper() == "TASK" else query

        # Command: profile/mode auto-derived from -p; --e2e handles new session + auto done + exit
        cmd = [
            sys.executable,
            str(self.cli_path / "main.py"),
            "agent",
            "-p", project_id,
            "-s", session_id,
            "--e2e",
            "-m", effective_query,
        ]

        print(f"[Runner] Mode: {mode.upper()}")
        print(f"[Runner] Executing query: '{effective_query}'")
        print(f"[Runner] Command: {' '.join(cmd)}")

        # Start Subprocess (use process group for clean timeout cleanup)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cli_path.parent),  # Root of ContextBot
            start_new_session=True,
        )

        try:
            # Wait for agent completion or timeout
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)

            out_str = stdout.decode('utf-8') if stdout else ""
            err_str = stderr.decode('utf-8') if stderr else ""

            if process.returncode != 0:
                print(f"[Runner] Process exited with error code {process.returncode}")
                if err_str:
                    print(f"Stderr:\n{err_str}")

            return out_str, process.returncode

        except asyncio.TimeoutError:
            print(f"[Runner] Timeout reached ({timeout_sec}s). Terminating agent process group.")
            # Send SIGTERM to the entire process group to clean up child processes
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown didn't work
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    process.kill()
                await process.wait()
            return "[TIMEOUT]", -1


async def run_evaluation(case_yaml_path: str, contextbot_root: str,
                         batch_timestamp: str | None = None):
    root_path = Path(contextbot_root)
    workspace_path = root_path / "workspace"
    cli_path = root_path / "cli"
    runs_path = root_path / "tests" / "runs"

    with open(case_yaml_path, 'r', encoding='utf-8') as f:
        case_config = yaml.safe_load(f)

    print(f"========== Starting E2E Eval: {case_config.get('name', 'Unknown')} ==========")

    env = TestEnvironment(workspace_path, case_config)

    # Snapshot fixture BEFORE setup() writes project.yaml or the agent touches anything
    snapshot = SnapshotManager(workspace_path, runs_path, env.project_id,
                               batch_timestamp=batch_timestamp)
    snapshot.snapshot()

    project_id, session_id = env.setup()

    runner = E2ERunner(cli_path)

    query = case_config.get('query', '')
    timeout = case_config.get('timeout_sec', 10800)
    mode = case_config.get('mode', 'NORMAL')

    # Execute query
    start_time = datetime.now()
    stdout, returncode = await runner.run_case(project_id, session_id, query, timeout_sec=timeout, mode=mode)
    elapsed = (datetime.now() - start_time).total_seconds()

    timed_out = stdout == "[TIMEOUT]"
    run_result = {
        "case": case_config.get('name', 'Unknown'),
        "project_id": project_id,
        "session_id": session_id,
        "mode": mode,
        "status": "timeout" if timed_out else "error" if (returncode != 0 or not stdout) else "completed",
        "elapsed_sec": round(elapsed, 1),
        "timeout_sec": timeout,
        "timestamp": start_time.isoformat(),
    }

    # Archive modified workspace + metadata, then restore original fixture
    archive_dir = snapshot.archive_and_restore(run_result, stdout)

    print(f"\n[Runner] Execution {'timed out' if timed_out else 'completed'} in {elapsed:.1f}s.")
    print(f"[Runner] Archive: {archive_dir}")
    print(f"[Runner] Agent trace: {archive_dir}/workspace/{session_id}/.bot/memory/events/")
    print("========================================================================\n")

    return {
        "case": run_result["case"],
        "project_id": project_id,
        "session_id": session_id,
        "mode": run_result["mode"],
        "status": run_result["status"],
        "elapsed_sec": run_result["elapsed_sec"],
        "archive_dir": archive_dir,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run E2E agent evaluation case.")
    parser.add_argument("case_file", help="Path to the YAML test case configuration")
    parser.add_argument("--root", default=".", help="Path to ContextBot root directory")

    args = parser.parse_args()

    asyncio.run(run_evaluation(args.case_file, args.root))
