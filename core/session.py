"""Session: 项目内的一次工作会话。

提供 metadata 管理、路径解析、写入路由和 subagent 隔离。
设计文档: bot_doc/design_doc/v2_project_abstraction/03_PATH_RESOLUTION.md
"""

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.project import Project


def generate_session_id(project_root: Path = None) -> str:
    """生成 MMDD_NN 格式的 session ID。

    扫描 project_root 下已有的 session 目录，找到当天最大序号 +1。
    如果 project_root 为 None 或不存在，序号从 01 开始。
    """
    today = datetime.now().strftime("%m%d")
    prefix = f"{today}_"
    max_seq = 0

    if project_root and project_root.exists():
        for d in project_root.iterdir():
            if d.is_dir() and d.name.startswith(prefix):
                try:
                    seq = int(d.name[len(prefix):])
                    max_seq = max(max_seq, seq)
                except ValueError:
                    pass

    return f"{prefix}{max_seq + 1:02d}"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OverlayFile:
    """overlay 中的一个文件。"""
    relative: str
    absolute: Path


@dataclass
class MergeReport:
    agent_name: str
    merged: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session:
    """项目内的一次工作会话。

    主 Agent (Assistant): Session 只管 metadata，文件操作走 Project。
    Subagent (Worker): Session 提供 overlay 隔离，文件操作走 Session.resolve()。
    """

    _SKIP_COPY = {".bot", ".git", "__pycache__", ".DS_Store", "subagents",
                  "task_workers", "_task_workers", "_subagent_results"}

    def __init__(self, project: "Project", session_id: str, role_type: str = "Assistant"):
        # Ensure session_id and role_type are strings (handle Typer OptionInfo)
        if hasattr(session_id, "default"):
            session_id = str(session_id.default)
        elif not isinstance(session_id, str):
            session_id = str(session_id)

        if hasattr(role_type, "default"):
            role_type = str(role_type.default)
        elif not isinstance(role_type, str):
            role_type = str(role_type)

        self.project = project
        self.id = session_id
        self._role_type = role_type

        self.root = project.root / session_id
        self.metadata = self.root / ".bot"
        self.metadata.mkdir(parents=True, exist_ok=True)

        # Subagent registry（session 级别，内存）
        self._subagent_registry: dict[str, dict] = {}

        # Protected prefixes: top-level dirs that are read-only (injected deps)
        self._protected_prefixes: frozenset[str] = frozenset()

    # -- Copy-on-Init --

    def init_overlay(self) -> int:
        """浅拷贝 core 文件到 overlay。仅 Worker 使用。"""
        core = self.project.core
        if not core.exists():
            return 0
        count = 0
        for src in core.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(core)
            if any(p in self._SKIP_COPY or p.startswith(".") for p in rel.parts):
                continue
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1
        logger.debug(f"init_overlay: copied {count} files from core to {self.root}")
        return count

    @staticmethod
    def _diff_overlay(session: "Session") -> list[OverlayFile]:
        """返回 overlay 中相对 core 新增或修改的文件（SHA-256 比较）。"""
        import hashlib

        def _hash(path: Path) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()

        changed = []
        for f in Session._walk_overlay(session):
            core_file = session.project.core / f.relative
            if not core_file.exists() or _hash(f.absolute) != _hash(core_file):
                changed.append(f)
        return changed

    # -- 路径解析 --

    def resolve(self, path: str) -> Path:
        """将 agent 的相对路径映射到物理路径。"""
        if ".." in Path(path).parts:
            raise PermissionError(f"Path traversal blocked: {path}")
        if Path(path).is_absolute():
            raise PermissionError(f"Absolute path blocked: {path}")

        if self._role_type == "Worker":
            # overlay 已有完整拷贝，直接返回
            return self.root / path

        # Assistant: 走 core（与 Project.resolve() 一致，不做 symlink resolve）
        return self.project.core / path

    def write_target(self, path: str) -> Path:
        """决定文件写到哪里，返回物理路径。"""
        if ".." in Path(path).parts:
            raise PermissionError(f"Path traversal blocked: {path}")

        # Block writes into read-only dependency directories
        if self._protected_prefixes:
            top_dir = Path(path).parts[0] if Path(path).parts else ""
            if top_dir in self._protected_prefixes:
                raise PermissionError(
                    f"Write blocked: '{path}' is inside read-only dependency directory '{top_dir}/'. "
                    f"Write your own files using simple filenames."
                )

        # Worker: 写 overlay（隔离）
        if self._role_type == "Worker":
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            # Fix read-only files copied from dependencies via bash cp
            if target.exists() and not os.access(target, os.W_OK):
                os.chmod(target, 0o644)
            return target

        # Assistant: 直写 core
        target = self.project.core / path
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    # -- Subagent 管理 --

    def register_subagent(self, name: str, config: dict):
        """注册子代理配置（session 级别，内存）。"""
        self._subagent_registry[name] = config

    def get_subagent(self, name: str) -> Optional[dict]:
        return self._subagent_registry.get(name)

    def merge_child(self, child_session: "Session", agent_name: str, merge_to_core: bool = False, diff_only: bool = False) -> MergeReport:
        """将子 session 的 overlay 产出合并。

        Args:
            merge_to_core: True → 直接写入 project core（适合修改论文等场景），
                           False → 写入 core/_subagent_results/（默认，需主 agent 审阅）。
            diff_only: True → 只合并相对 core 有变更的文件（copy-on-init 模式）。
        """
        report = MergeReport(agent_name=agent_name)
        files = self._diff_overlay(child_session) if diff_only else self._walk_overlay(child_session)
        for f in files:
            if merge_to_core:
                target = self.project.core / f.relative
            else:
                target = self.project.core / "_subagent_results" / agent_name / f.relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f.absolute, target)
            report.merged.append(f.relative)

            # merge_to_core 时追踪 pending writes 以触发 auto commit
            if merge_to_core:
                self.project._pending_writes.append(f.relative)

        return report

    @staticmethod
    def _walk_overlay(session: "Session") -> list[OverlayFile]:
        """扫描 session root 中的非 metadata 文件。"""
        files = []
        if not session.root.exists():
            return files
        for f in session.root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(session.root)
            # 跳过 metadata 和隐藏目录
            parts = rel.parts
            if any(p.startswith(".") or p in ("subagents", "task_workers", "_task_workers") for p in parts):
                continue
            files.append(OverlayFile(relative=str(rel), absolute=f))
        return files

    def cleanup_subagent(self, task_id: str):
        """清理子代理的工作目录。"""
        subagent_dir = self.root / "subagents" / task_id
        if subagent_dir.exists():
            shutil.rmtree(subagent_dir)

    def cleanup_all_subagents(self):
        """清理所有子代理工作目录。"""
        subagents_dir = self.root / "subagents"
        if subagents_dir.exists():
            shutil.rmtree(subagents_dir)
            subagents_dir.mkdir()

    # -- Trace & History --

    def history_logger(self):
        """返回 HistoryLogger 实例。"""
        from agent.memory.logger import HistoryLogger
        return HistoryLogger(self.metadata)

    def trace_logger(self):
        """返回 TraceLogger 实例。"""
        from agent.memory.trace import TraceLogger
        events_dir = self.metadata / "events"
        return TraceLogger(events_dir, self.id)
