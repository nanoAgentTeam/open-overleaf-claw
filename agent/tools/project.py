"""Tools for project and session navigation and management."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from loguru import logger

from core.tools.base import BaseTool

if TYPE_CHECKING:
    from agent.services.tool_context import ToolContext


class ProjectTool(BaseTool):
    """Project management tool."""
    def __init__(self, tool_context: "ToolContext"):
        self.ctx = tool_context
        self.workspace = Path(tool_context.workspace)

    @property
    def name(self) -> str:
        return "project_manager"

    @property
    def description(self) -> str:
        return (
            "项目管理工具（仅在 Default 工作区可用，switch 进入项目后此工具不可用）。\n"
            "正确流程：create → link_overleaf（可选）→ switch。必须在 switch 之前完成所有配置。\n"
            "- list: 列出工作区中的所有项目。\n"
            "- create: 创建新项目（不会自动切换）。\n"
            "- link_overleaf: 关联 Overleaf 项目并拉取文件。必须在 switch 之前调用。不传 overleaf_id 时列出可选的 Overleaf 项目。\n"
            "- info: 查看指定项目的配置和状态（git、overleaf、main_tex 等）。\n"
            "- switch: 切换到指定项目，进入工作模式。切换后此工具将不可用。"
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "switch", "info", "link_overleaf"],
                    "description": "执行的动作。"
                },
                "project_name": {
                    "type": "string",
                    "description": "项目名称。create/switch/info/link_overleaf 时需要。"
                },
                "session_name": {
                    "type": "string",
                    "description": "会话名称（可选）。不传则自动生成 MMDD_NN 格式（如 0217_01）。也可传入已有 session 名称来恢复。"
                },
                "overleaf_id": {
                    "type": "string",
                    "description": "Overleaf 项目 ID（URL 中的 ID）。用于 link_overleaf。"
                },
            },
            "required": ["action"],
        }

    def _get_project_path(self, project_name: str) -> Path:
        return self.workspace / project_name

    async def execute(self, action: str, project_name: Optional[str] = None,
                      session_name: Optional[str] = None, overleaf_id: Optional[str] = None,
                      **kwargs) -> str:
        if action == "list":
            return self._list()
        elif action == "create":
            if not project_name:
                return "[ERROR] 'project_name' is required."
            return await self._create(project_name)
        elif action == "switch":
            if not project_name:
                return "[ERROR] 'project_name' is required."
            # session_name=None lets switch_project reuse today's latest session
            return await self._switch(project_name, session_name)
        elif action == "info":
            if not project_name:
                return "[ERROR] 'project_name' is required."
            return self._info(project_name)
        elif action == "link_overleaf":
            if not project_name:
                return "[ERROR] 'project_name' is required."
            return await self._link_overleaf(project_name, overleaf_id)
        else:
            return f"[ERROR] Unknown action '{action}'"

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def _list(self) -> str:
        if not self.workspace.exists():
            return "工作区为空。使用 create 创建新项目。"
        current = self.ctx.project_id
        projects = []
        for d in sorted(self.workspace.iterdir()):
            if not d.is_dir() or d.name in ("Default",) or d.name.startswith("."):
                continue
            config_path = d / "project.yaml"
            overleaf_tag = ""
            if config_path.exists():
                try:
                    import yaml
                    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                    if cfg.get("overleaf", {}).get("project_id"):
                        overleaf_tag = " [Overleaf]"
                except Exception:
                    pass
            active_tag = " ← 当前" if d.name == current else ""
            projects.append(f"  {d.name}{overleaf_tag}{active_tag}")

        if not projects:
            return "工作区没有项目。使用 create 创建新项目。"
        header = f"项目列表 (当前: {current}):"
        return header + "\n" + "\n".join(projects)

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    async def _create(self, project_name: str) -> str:
        from core.project import Project
        from core.automation.bootstrap import ensure_project_automation_jobs

        project_path = self._get_project_path(project_name)
        if project_path.exists():
            return f"[ERROR] Project '{project_name}' already exists. Use 'switch' to enter it."

        proj = Project(project_name, self.workspace)
        bootstrap = ensure_project_automation_jobs(proj)
        created = int((bootstrap.get("radar_applied") or {}).get("created", 0))
        created_autoplan = bool(bootstrap.get("created_autoplan"))
        autoplan_line = await self._run_initial_autoplan(proj)

        bootstrap_line = "  3. Default radar jobs initialized."
        if not created_autoplan and created == 0:
            bootstrap_line = "  3. Default radar jobs already present."
        try:
            from config.diagnostics import is_overleaf_logged_in
            ol_logged_in = is_overleaf_logged_in()
        except Exception:
            ol_logged_in = False

        if ol_logged_in:
            overleaf_step = f"  1. (Recommended) Use 'link_overleaf' with project_name='{project_name}' to associate an Overleaf project."
        else:
            overleaf_step = (
                f"  1. (Optional) To sync with Overleaf, an admin needs to run "
                f"'ols login' on the server first."
            )

        lines = [
            f"Project '{project_name}' created. You are still in the Default workspace.\n"
            f"Next steps (all done here in Default):\n"
            f"{overleaf_step}\n"
            f"  2. Use 'switch' with project_name='{project_name}' to enter the project.\n"
            f"{bootstrap_line}",
        ]
        if autoplan_line:
            lines.append(autoplan_line)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # switch
    # ------------------------------------------------------------------

    async def _switch(self, project_name: str, session_name: str = None) -> str:
        project_path = self._get_project_path(project_name)
        if not project_path.exists():
            return f"[ERROR] Project '{project_name}' does not exist."

        # If session_name is provided, ensure the directory exists
        if session_name:
            session_path = project_path / session_name
            if not session_path.exists():
                session_path.mkdir(parents=True, exist_ok=True)
                (session_path / ".bot").mkdir(exist_ok=True)
                (session_path / "artifacts").mkdir(exist_ok=True)
                (session_path / "subagents").mkdir(exist_ok=True)

        try:
            if hasattr(self.ctx, 'switch_project_fn') and self.ctx.switch_project_fn:
                await self.ctx.switch_project_fn(project_name, session_name)
            else:
                await self.ctx.switch_mode("NORMAL", project_id=project_name, session_id=session_name)
            # Get actual session_id (may have been resolved by switch_project)
            actual_session = getattr(self.ctx, 'session_id', session_name) or session_name
            msg = (
                f"Switched to [{project_name}/{actual_session}].\n"
                f"Your working directory is now the project core. "
                f"Use '.' or filenames directly (e.g. 'main.tex'), do NOT prefix with '{project_name}/'."
            )

            # Append Overleaf sync hint if applicable
            try:
                from core.project import Project
                from config.diagnostics import is_overleaf_logged_in
                proj = Project(project_name, self.workspace)
                ol_cfg = getattr(proj.config, "overleaf", None)
                has_link = bool(ol_cfg and getattr(ol_cfg, "project_id", None))
                if has_link:
                    if is_overleaf_logged_in():
                        msg += (
                            "\nThis project is linked to Overleaf. "
                            "Consider running /sync pull to get the latest changes."
                        )
                    else:
                        msg += (
                            "\nThis project has an Overleaf link but .olauth is missing. "
                            "Sync will fail until login."
                        )
            except Exception:
                pass

            # Append quick commands guide
            msg += (
                "\n\n📖 常用命令："
                "\n  /compile — 编译 PDF"
                "\n  /sync pull — 从 Overleaf 拉取"
                "\n  /sync push — 推送到 Overleaf"
                "\n  /git — Git 版本管理"
                "\n  /task <目标> — 启动任务会话"
                "\n  /help — 查看全部命令"
            )

            return msg
        except Exception as e:
            return f"[ERROR] switching: {e}"

    # ------------------------------------------------------------------
    # info
    # ------------------------------------------------------------------

    def _info(self, project_name: str) -> str:
        from core.project import Project

        project_path = self._get_project_path(project_name)
        if not project_path.exists():
            return f"[ERROR] Project '{project_name}' not found."

        try:
            proj = Project(project_name, self.workspace)
        except Exception as e:
            return f"[ERROR] Loading project: {e}"

        cfg = proj.config
        lines = [f"Project: {project_name}"]
        lines.append(f"  main_tex: {cfg.main_tex}")
        lines.append(f"  strategy: {cfg.strategy}")
        lines.append(f"  git: {'enabled' if cfg.git.enabled else 'disabled'}"
                      f" (auto_commit={'on' if cfg.git.auto_commit else 'off'})")

        if cfg.overleaf and cfg.overleaf.project_id:
            lines.append(f"  overleaf: linked (ID: {cfg.overleaf.project_id})")
        else:
            lines.append(f"  overleaf: not linked")

        if cfg.latex:
            lines.append(f"  latex: {cfg.latex.engine}")
        else:
            lines.append(f"  latex: default (pdflatex)")

        sessions = []
        for d in project_path.iterdir():
            if d.is_dir() and d.name != project_name and not d.name.startswith("."):
                mtime = d.stat().st_mtime
                sessions.append((d.name, mtime))
        sessions.sort(key=lambda x: x[1], reverse=True)  # 最新的在前

        if sessions:
            from datetime import datetime
            session_lines = []
            for name, mtime in sessions:
                ts = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
                session_lines.append(f"{name} ({ts})")
            lines.append(f"  sessions (newest first): {', '.join(session_lines)}")
        else:
            lines.append(f"  sessions: none")

        core = proj.core
        if core.exists():
            files = [f.name for f in core.iterdir() if not f.name.startswith(".")][:15]
            lines.append(f"  files: {', '.join(files) if files else 'empty'}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # link_overleaf
    # ------------------------------------------------------------------

    async def _link_overleaf(self, project_name: str, overleaf_id: Optional[str] = None) -> str:
        """Link an Overleaf project. If no overleaf_id, list available Overleaf projects."""
        from core.project import Project
        from core.automation.bootstrap import ensure_project_automation_jobs

        project_path = self._get_project_path(project_name)
        if not project_path.exists():
            return f"[ERROR] Project '{project_name}' does not exist. Create it first."

        if not overleaf_id:
            try:
                from agent.tools.overleaf import OverleafTool
                ol = OverleafTool(workspace=self.workspace)
                result = ol.execute(action="list")
                return f"Please provide an overleaf_id. Here are your Overleaf projects:\n{result}"
            except Exception as e:
                return f"[ERROR] Cannot list Overleaf projects: {e}\nPlease provide overleaf_id directly (from the Overleaf URL)."

        try:
            proj = Project(project_name, self.workspace)
            proj.link_overleaf(overleaf_id)
        except Exception as e:
            return f"[ERROR] Failed to save config: {e}"

        try:
            result = proj.sync_from_overleaf()
            if result.success:
                pulled = len(result.pulled) if result.pulled else 0
                bootstrap = ensure_project_automation_jobs(proj)
                created = int((bootstrap.get("radar_applied") or {}).get("created", 0))
                created_autoplan = bool(bootstrap.get("created_autoplan"))
                msg = f"Linked Overleaf (ID: {overleaf_id}) and pulled {pulled} files."
                if result.conflicts:
                    msg += f"\nConflicts: {', '.join(result.conflicts)}"
                if created_autoplan or created > 0:
                    msg += f"\nInitialized default radar jobs (autoplan={created_autoplan}, created={created})."
                autoplan_line = await self._run_initial_autoplan(proj)
                if autoplan_line:
                    msg += f"\n{autoplan_line}"
                return msg
            else:
                errors = ', '.join(result.errors) if result.errors else 'unknown'
                return f"Linked Overleaf to '{project_name}', but pull failed: {errors}\nRetry with /sync pull after switching."
        except Exception as e:
            return f"Linked Overleaf to '{project_name}' (config saved), but pull failed: {e}\nRetry with /sync pull after switching."

    async def _run_initial_autoplan(self, project: Any) -> str:
        provider = getattr(self.ctx, "provider", None)
        model = getattr(self.ctx, "model", None)
        if not provider:
            return ""

        try:
            from agent.radar_autopilot import RadarAutoplanService

            service = RadarAutoplanService(provider=provider, model=model)
            result = await service.reconcile_project(project, actor_job_id="radar.autoplan")
            applied = result.get("applied") or {}
            line = (
                "Initial autoplan applied "
                f"(upserted={int(applied.get('upserted', 0))}, "
                f"disabled={int(applied.get('disabled', 0))}, "
                f"skipped={int(applied.get('skipped', 0))})"
            )
        except Exception as e:
            logger.debug(f"Initial autoplan run skipped for {project.id}: {e}")
            return ""

        runtime = getattr(self.ctx, "automation_runtime", None)
        if runtime:
            try:
                await runtime.reschedule_project(project)
                line += ", scheduler reloaded"
            except Exception as e:
                logger.debug(f"Reschedule after initial autoplan failed for {project.id}: {e}")
        return line
