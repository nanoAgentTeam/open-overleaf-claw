"""Centralized workflow state management.

Single source of truth for project_id, session_id, research_id, task_id,
and all derived paths.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
from loguru import logger


class StateManager:
    """
    Manages all session/project state and derived paths.
    When state changes, all dependent paths are recomputed atomically.
    """

    def __init__(
        self,
        workspace: Path,
        project_id: str = "Default",
        session_id: str = "default",
        research_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata_root: Optional[Path] = None,
    ):
        self._workspace = workspace
        self._project_id = project_id
        self._session_id = session_id
        self._research_id = research_id
        self._task_id = task_id

        # Compute derived paths
        self._project_root = self._workspace / self._project_id
        self._session_root = self._project_root / self._session_id

        if metadata_root:
            self._metadata_root = metadata_root
        else:
            self._metadata_root = self._session_root / ".bot"

        self._metadata_root.mkdir(parents=True, exist_ok=True)

        # Global metadata (cross-project)
        self._global_metadata_root = self._workspace.parent / ".bot"
        self._global_metadata_root.mkdir(parents=True, exist_ok=True)

    # ---- read-only properties ----

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def research_id(self) -> Optional[str]:
        return self._research_id

    @property
    def task_id(self) -> Optional[str]:
        return self._task_id

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def session_root(self) -> Path:
        return self._session_root

    @property
    def metadata_root(self) -> Path:
        return self._metadata_root

    @property
    def global_metadata_root(self) -> Path:
        return self._global_metadata_root

    # ---- mutations ----

    def update_ids(
        self,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        research_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Update IDs and recompute all derived paths."""
        if project_id is not None:
            self._project_id = project_id
        if session_id is not None:
            self._session_id = session_id
        if research_id is not None:
            self._research_id = research_id
        if task_id is not None:
            self._task_id = task_id

        # Recompute
        self._project_root = self._workspace / self._project_id
        self._session_root = self._project_root / self._session_id
        self._metadata_root = self._session_root / ".bot"
        self._metadata_root.mkdir(parents=True, exist_ok=True)

        self._global_metadata_root = self._workspace.parent / ".bot"
        self._global_metadata_root.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"StateManager: IDs updated -> project={self._project_id}, "
            f"session={self._session_id}, research={self._research_id}, task={self._task_id}"
        )
