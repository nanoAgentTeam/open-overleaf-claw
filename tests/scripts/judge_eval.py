import sys
import json
import yaml
import asyncio
import subprocess
import os
from datetime import datetime
from pathlib import Path

E2E_JUDGE_MODEL = os.environ.get("E2E_JUDGE_MODEL", "sonnet")

# Allow importing project config when running from repo root
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Default metadata directory name used by the agent
DEFAULT_METADATA_DIR = ".bot"


class JudgeEvaluator:
    """
    通过 Claude Code CLI 子进程执行 E2E 评测。

    Claude Code 会在 archive 目录下，用自带的 Read/Grep/Glob 工具
    主动检查 trace 文件和 LaTeX 产物，而不是被动接受拼好的 transcript 文本。

    优势：
    - 不受 token 限制（Claude 按需读文件）
    - 无需 litellm / OpenAI-compatible 配置
    - 直接使用本机已登录的 Claude Code 账号
    """

    def __init__(self, model: str = None):
        self.model = model or E2E_JUDGE_MODEL

    # ------------------------------------------------------------------
    # Rule-based compile check (W tasks only)
    # ------------------------------------------------------------------

    def compile_check(self, archive_dir: Path, case_config: dict) -> dict:
        """Compile the archived project and return {success, errors, log}."""
        project_id = case_config.get("project_id", "")
        main_tex = case_config.get("main_tex", "main.tex")
        core_dir = archive_dir / "workspace" / project_id

        if not core_dir.exists():
            return {"success": False, "errors": [f"Core dir not found: {core_dir}"], "log": ""}

        tex_file = core_dir / main_tex
        if not tex_file.exists():
            return {"success": False, "errors": [f"{main_tex} not found"], "log": ""}

        engine = self._detect_latex_engine(tex_file)
        try:
            cmd = ["latexmk", f"-{engine}", "-interaction=nonstopmode", "-f", "-quiet", main_tex]
            proc = subprocess.run(cmd, cwd=str(core_dir), capture_output=True, text=True, timeout=120)
            success = proc.returncode == 0

            log_file = core_dir / main_tex.replace(".tex", ".log")
            errors = []
            if log_file.exists():
                for line in log_file.read_text(errors="replace").splitlines():
                    if line.startswith("!") or (": error:" in line.lower()):
                        errors.append(line)

            return {
                "success": success,
                "errors": errors[:10],
                "log": (proc.stdout + proc.stderr)[-800:] if not success else "",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "errors": ["Compilation timed out (120s)"], "log": ""}
        except FileNotFoundError:
            return {"success": False, "errors": ["latexmk not found on PATH"], "log": ""}
        except Exception as e:
            return {"success": False, "errors": [str(e)], "log": ""}

    @staticmethod
    def _detect_latex_engine(tex_path: Path) -> str:
        try:
            content = tex_path.read_text(errors="replace")[:3000]
            if "xeCJK" in content or "xelatex" in content.lower():
                return "xelatex"
            if "luatex" in content.lower() or "lualatex" in content.lower():
                return "lualatex"
        except Exception:
            pass
        return "pdf"

    # ------------------------------------------------------------------
    # Main evaluate entry point
    # ------------------------------------------------------------------

    async def evaluate(self, session_dir: Path, case_config: dict,
                       archive_dir: Path = None, root_path: Path = None,
                       report_path: Path = None):
        """Run Claude Code judge over the session artifacts."""
        if not session_dir.exists():
            print(f"[Judge] Session directory not found: {session_dir}")
            return None

        # Determine working directory and relative paths for Claude Code.
        #
        # Batch mode (archive_dir provided):
        #   cwd = archive_dir
        #   session_dir = archive_dir/workspace/{session_id}/.bot
        #   events  → workspace/{session_id}/.bot/memory/events/
        #   latex   → workspace/{project_id}/
        #
        # Standalone mode (no archive_dir):
        #   session_dir = workspace/{project_id}/{session_id}/.bot
        #   cwd = workspace/{project_id}/
        #   events  → {session_id}/.bot/memory/events/
        #   latex   → {project_id}/   (core dir)

        project_id = case_config.get("project_id", "")

        if archive_dir and archive_dir.exists():
            cwd = archive_dir
            events_rel = session_dir.relative_to(archive_dir) / "memory" / "events"
            latex_rel = Path("workspace") / project_id
        else:
            cwd = session_dir.parent.parent          # workspace/{project_id}/
            events_rel = session_dir.relative_to(cwd) / "memory" / "events"
            latex_rel = Path(project_id)

        events_dir = cwd / events_rel
        if not events_dir.exists():
            print(f"[Judge] Events directory not found: {events_dir}")
            return None

        jsonl_files = sorted(events_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not jsonl_files:
            print(f"[Judge] No jsonl trace found in {events_dir}")
            return None

        if jsonl_files[0].stat().st_size == 0:
            print(f"[Judge] Trace file is empty: {jsonl_files[0]}")
            return None

        # Rule-based compile check for Write tasks
        is_write_task = project_id.replace("E2E_Test_", "").startswith("W")
        compile_result = None
        if is_write_task and archive_dir and archive_dir.exists():
            print("[Judge] 🔨 Running compile check on archived project...")
            compile_result = self.compile_check(archive_dir, case_config)
            status_icon = "✅" if compile_result["success"] else "❌"
            print(f"[Judge] Compile: {status_icon} {'PASS' if compile_result['success'] else 'FAIL'}")

        prompt = self._build_prompt(case_config, events_rel, latex_rel, compile_result, is_write_task)

        print("\n[Judge] 🧠 Launching Claude Code judge...")

        raw = await self._call_claude_code(prompt, cwd=str(cwd))
        if raw is None:
            return None

        evaluation_result = self._parse_response(raw)

        # Save report
        if report_path is None:
            if root_path is None:
                root_path = session_dir.parent.parent.parent
            report_path = root_path / "tests" / "results" / f"{session_dir.name}_evaluation.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Evaluation Report: {case_config.get('name')}\n\n")
            if compile_result is not None:
                f.write("## ⚙️ 编译验证（Compile Check）\n\n")
                if compile_result["success"]:
                    f.write("**✅ 编译成功** — LaTeX 项目编译通过，PDF 生成正常。\n\n")
                else:
                    f.write("**❌ 编译失败** — LaTeX 项目编译未通过。\n\n")
                    if compile_result["errors"]:
                        f.write("**错误信息：**\n```\n")
                        f.write("\n".join(compile_result["errors"]))
                        f.write("\n```\n\n")
                    if compile_result.get("log"):
                        f.write(f"**编译日志（末尾）：**\n```\n{compile_result['log']}\n```\n\n")
                f.write("---\n\n")
            f.write(evaluation_result)

        print(f"[Judge] ✅ Evaluation complete! Report saved to: {report_path}")
        return report_path

    # ------------------------------------------------------------------
    # Claude Code CLI call
    # ------------------------------------------------------------------

    async def _call_claude_code(self, prompt: str, cwd: str) -> str | None:
        """
        调用 claude CLI 的 print 模式，返回 result 文本。

        关键：
        - --output-format json  → 输出 JSON 包装，result 字段是 Claude 的回复文本
        - --max-turns 30        → 允许 Claude 多轮读文件再作答
        - 去掉 CLAUDECODE 环境变量，防止嵌套调用被拒绝
        """
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", prompt,
                "--model", self.model,
                "--output-format", "json",
                "--max-turns", "30",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            raw = stdout.decode("utf-8")

            if not raw.strip():
                err = stderr.decode("utf-8")
                print(f"[Judge] ❌ Claude Code returned empty output. stderr: {err[:500]}")
                return None

            return raw

        except asyncio.TimeoutError:
            print("[Judge] ❌ Claude Code judge timed out (300s)")
            return None
        except FileNotFoundError:
            print("[Judge] ❌ 'claude' command not found. Please install Claude Code CLI.")
            return None
        except Exception as e:
            print(f"[Judge] ❌ Unexpected error calling Claude Code: {e}")
            return None

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> str:
        """
        从 --output-format json 的输出中提取 Claude 的回复文本。

        输出格式：{"type": "result", "subtype": "success", "result": "...markdown...", ...}
        """
        try:
            outer = json.loads(raw)
            if outer.get("subtype") == "error_max_turns":
                return "_Judge 超过最大轮数限制，评测已跳过。_"
            content = outer.get("result", "").strip()
            return content if content else "_Judge 返回空结果。_"
        except (json.JSONDecodeError, AttributeError):
            # 非 JSON 输出时直接返回原始内容
            return raw.strip() or "_Judge 无输出。_"

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_prompt(self, case_config: dict, events_rel: Path, latex_rel: Path,
                      compile_result: dict = None, is_write_task: bool = False) -> str:
        expected = yaml.dump(case_config.get('expected_outcome', []), allow_unicode=True)
        query = case_config.get('query', '')
        current_date = datetime.now().strftime("%Y-%m-%d")

        compile_section = ""
        compile_scoring_note = ""
        if compile_result is not None:
            if compile_result["success"]:
                compile_section = "\n**COMPILE CHECK（规则验证）: ✅ PASS** — LaTeX 项目编译成功。\n"
            else:
                errors_str = "\n".join(compile_result["errors"]) if compile_result["errors"] else "（见日志）"
                compile_section = (
                    f"\n**COMPILE CHECK（规则验证）: ❌ FAIL** — LaTeX 项目编译失败。\n"
                    f"错误：\n```\n{errors_str}\n```\n"
                )
            compile_scoring_note = (
                "\n5. **编译结果（Compile Result）:** 独立规则评测维度（已通过实际编译验证，非推断）。"
                "编译成功是 Writing 任务的硬性要求。"
                "❌ 编译失败直接扣 2 分；✅ 编译成功不额外加分（视为基本要求）。"
                "请在报告中单独列出此维度结论。\n"
            )

        latex_read_instruction = ""
        if is_write_task:
            latex_read_instruction = f"""
请同时读取 `{latex_rel}/` 下的 LaTeX 文件（尤其是 main.tex 及相关章节文件），
检查 agent 实际修改了哪些内容，修改是否符合用户指令和预期结果。
"""

        return f"""你是 AI Agent 系统的资深 QA 评测专家，请对以下 E2E 测试结果进行深度评测。

## 评测上下文

**当前日期**: {current_date}
所有 ≤{current_date} 的日期均指真实存在的论文/事件，不要视为虚构。

**数据来源（真实 API，返回真实数据）**:
- arxiv_search、openalex_search、pubmed_search、web_search 均调用真实外部 API
- 工具返回的论文（包括 2025/2026 年）都是真实存在的，不要因此扣分
{compile_section}
**预期环境行为（不扣分）**:
- `notify_push` 返回 "no channels configured" — 测试环境无推送配置，属正常
- `read_file` 阻止沙盒外绝对路径 — 安全限制，属正常
- 搜索结果部分不相关 — agent 识别并重试即可

---

## 测试任务

**用户指令**:
{query}

**预期结果**:
{expected}

---

## 目录结构

当前工作目录是本次测试的完整 archive 快照：

- **Agent 执行 trace**: `{events_rel}/` 目录下的 `.jsonl` 文件
- **LaTeX 项目文件**: `{latex_rel}/` 目录（agent 修改后的最终状态）

### Trace JSONL 格式（每行一个 JSON 事件）

| type | 含义 | 关键字段 |
|---|---|---|
| `turn_start` | 用户请求开始 | `data.inbound` |
| `tool_call` | Agent 调用工具 | `tool`（工具名）, `tool_args`（参数） |
| `tool_result` | 工具返回结果 | `data.output` |
| `error` | 错误事件 | `data.error` |
| `turn_end` | 本轮结束 | `data.outbound`（Agent 最终回复） |

---

## 你的任务

**第一步**：读取 trace 文件（`{events_rel}/` 下的 `.jsonl`），了解 agent 的完整执行过程。
{latex_read_instruction}
**第二步**：按以下维度评测，用清晰的 Markdown 格式输出报告（**全程中文**）：

1. **目标达成度（Goal Adherence）**: Expected Outcomes 各项是否完成？逐项 YES/NO 并说明（不因预期环境行为扣分）。
2. **效率与逻辑（Efficiency & Logic）**: 是否存在无效循环、工具误用、逻辑断裂？
3. **Bug / 错误检测（Bug / Error Detection）**: 是否遭遇真实环境 Bug（排除预期行为）？是否有合理恢复？{compile_scoring_note}
4. **最终评语与评分（Final Verdict）**: 综合评分 X/10，一句话总结。评分标准：
   - 9-10: 全部目标达成，输出质量高，无明显缺陷
   - 7-8: 主要目标达成，有小瑕疵但不影响整体价值
   - 5-6: 部分目标达成，有明显缺陷但有实质产出
   - 3-4: 大部分目标未达成，输出价值有限
   - 1-2: 基本失败，几乎无有效产出

**请务必先读取文件，再根据实际内容评分，不要基于假设。**
"""


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def run_judge(case_yaml_path: str, contextbot_root: str, session_id: str,
                    metadata_dir: str = DEFAULT_METADATA_DIR):
    root_path = Path(contextbot_root)
    workspace_path = root_path / "workspace"

    with open(case_yaml_path, 'r', encoding='utf-8') as f:
        case_config = yaml.safe_load(f)

    project_id = case_config.get('project_id', 'E2E_TestProject')
    session_dir = workspace_path / project_id / session_id / metadata_dir

    judge = JudgeEvaluator()
    await judge.evaluate(session_dir, case_config, root_path=root_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate a completed E2E session using Claude Code Judge.")
    parser.add_argument("case_file", help="Path to the YAML test case configuration")
    parser.add_argument("session_id", help="The Session ID (e.g., 0225_E2E) that was executed")
    parser.add_argument("--root", default=".", help="Path to ContextBot root directory")
    parser.add_argument("--model", default="sonnet", help="Claude model to use for judging (default: sonnet)")
    parser.add_argument("--metadata-dir", default=DEFAULT_METADATA_DIR,
                        help=f"Name of the metadata directory inside each session (default: {DEFAULT_METADATA_DIR})")

    args = parser.parse_args()

    asyncio.run(run_judge(args.case_file, args.root, args.session_id,
                          metadata_dir=args.metadata_dir))
