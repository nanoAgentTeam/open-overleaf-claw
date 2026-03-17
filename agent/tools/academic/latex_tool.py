"""LaTeX compilation tool — compile-fix agent that iteratively fixes errors."""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

from loguru import logger
from core.tools.base import BaseTool


# System prompt for the internal fix agent (compilation errors)
_FIX_ERROR_SYSTEM_PROMPT = """\
You are a LaTeX compilation error fixer. You receive compilation errors and the log tail, and must fix them.

Strategy:
1. FIRST, read the FULL error list and log tail to understand ALL issues before fixing anything.
2. Prioritize errors by severity:
   a. Missing files (\\input, \\include, \\lstinputlisting referencing non-existent files) — comment out or remove the line.
   b. Document class requirements (e.g., acmart requiring \\country{} in \\affiliation) — add the required fields.
   c. Package conflicts (e.g., loading hyperref when the class already loads it) — remove the redundant \\usepackage.
   d. Syntax errors (mismatched environments, undefined commands) — fix the syntax.
3. Use list_files to check what files actually exist before assuming a file is available.
4. Fix as MANY errors as possible in one round, not just the first one you see.
5. Use PARALLEL tool calls: you can call multiple read_file or str_replace in a single turn to speed up.

Rules:
- Read the relevant .tex files BEFORE making changes.
- Fix ONLY the compilation errors. Do NOT rewrite or restructure content.
- Apply minimal, targeted fixes using str_replace.
- For missing external files (\\lstinputlisting, \\includegraphics with non-existent paths), comment out or remove the problematic line.
- After applying fixes, respond with a brief summary of what you changed.
- If you cannot fix an error (e.g., missing package not installable), explain why.
"""

# System prompt for the internal fix agent (content-correctness warnings)
_FIX_WARNING_SYSTEM_PROMPT = """\
You are a LaTeX warning fixer. The document compiled successfully but has content-correctness warnings that need fixing.

You handle these warning types:
1. **Undefined citation** (`Citation 'xxx' undefined`): The \\cite key doesn't match any \\bibitem or .bib entry.
   - Read the .bib file (or \\bibitem section) to find the correct key. Fix typos in \\cite{}.
   - If the entry truly doesn't exist, add a placeholder \\bibitem or comment out the \\cite.
2. **Undefined reference** (`Reference 'xxx' undefined`): A \\ref{xxx} or \\eqref{xxx} has no matching \\label{xxx}.
   - Check if the \\label exists with a different name (typo). Fix the \\ref or add the missing \\label.
3. **Multiply defined label** (`Label 'xxx' multiply defined`): The same \\label{xxx} appears more than once.
   - Read both locations and rename one to be unique.

Rules:
- Read the relevant files FIRST to understand context before making changes.
- Apply minimal, targeted fixes. Do NOT restructure or rewrite content.
- For .bib files, also check if the file is included via \\bibliography{} or \\addbibresource{}.
- Use PARALLEL tool calls: you can call multiple read_file or str_replace in a single turn to speed up.
- After applying fixes, respond with a brief summary of what you changed.
"""

# Patterns for content-correctness warnings worth auto-fixing
_FIXABLE_WARNING_PATTERNS = [
    re.compile(r"Citation `(.+?)' on page \d+ undefined"),
    re.compile(r"Reference `(.+?)' on page \d+ undefined"),
    re.compile(r"Label `(.+?)' multiply defined"),
    re.compile(r"There were undefined references"),
    re.compile(r"There were multiply-defined labels"),
    re.compile(r"Package natbib Warning: Citation `(.+?)' on page \d+ undefined"),
]

# Tool schemas for the internal fix agent
_READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a .tex or .bib file to understand context around an error.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file."},
                "start_line": {"type": "integer", "description": "Start line (1-based)."},
                "end_line": {"type": "integer", "description": "End line (1-based)."},
            },
            "required": ["path"],
        },
    },
}

_STR_REPLACE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "str_replace",
        "description": "Replace a specific string in a file. old_string must match exactly once.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file."},
                "old_string": {"type": "string", "description": "Exact string to replace."},
                "new_string": {"type": "string", "description": "Replacement string."},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
}

_LIST_FILES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files in a directory. Useful to check what files exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path (use '.' for project root)."},
            },
            "required": ["path"],
        },
    },
}

_FIX_TOOLS = [_READ_FILE_SCHEMA, _STR_REPLACE_SCHEMA, _LIST_FILES_SCHEMA]


class LaTeXCompileTool(BaseTool):
    """
    Compile .tex to PDF with automatic error fixing.

    On compilation failure, spawns an internal LLM loop that reads errors,
    fixes the .tex source, and recompiles — up to MAX_FIX_ROUNDS times.
    """

    MAX_FIX_ROUNDS = 5

    def __init__(self, workspace_root: Path = None, session: Any = None,
                 project: Any = None, provider: Any = None, model: str = None, **kwargs):
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.session = session
        self.project = project
        self.provider = provider
        self.model = model

    @property
    def name(self) -> str:
        return "latex_compile"

    @property
    def description(self) -> str:
        return (
            "Compile a LaTeX file to PDF. If compilation fails, automatically "
            "analyzes errors and attempts to fix them (up to 5 rounds). "
            "Returns 'Success' with PDF path, or a summary of unfixable errors. "
            "IMPORTANT: Always provide main_file with the relative path to the "
            ".tex file (e.g. 'main.tex' or 'subdir/main.tex'). "
            "Omitting it may fail if the project structure is non-standard."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "main_file": {
                    "type": "string",
                    "description": (
                        "Relative path to the .tex file from the project core directory "
                        "(e.g. 'main.tex' or 'subdir/main.tex'). "
                        "You should always provide this parameter."
                    )
                }
            },
        }

    async def execute(self, main_file: str = None, **kwargs) -> str:
        if not self.project:
            if not main_file:
                return "[ERROR] main_file is required when no project context is available."
            return self._compile_fallback(main_file)

        # First compile attempt
        result = self._do_compile(main_file)

        # Compilation failed → error fix loop
        if not result.success:
            if not self.provider:
                return self._format_failure(result)
            result = await self._auto_fix_errors(result, main_file, kwargs.get("on_token"))
            if not result.success:
                return self._format_failure(result)

        # Compilation succeeded → check for fixable warnings
        fixable_warnings = self._extract_fixable_warnings(result.warnings)
        if fixable_warnings and self.provider:
            result = await self._auto_fix_warnings(result, fixable_warnings, main_file, kwargs.get("on_token"))

        return self._format_success(result)

    # ------------------------------------------------------------------
    # Internal compile helpers
    # ------------------------------------------------------------------

    def _do_compile(self, main_file: Optional[str]) -> "CompileResult":
        """Run a single compilation via Project."""
        from core.project import CompileResult
        if self.session and hasattr(self.session, '_role_type') and self.session._role_type == "Worker":
            tex_path = self.session.root / (main_file or self.project.config.main_tex)
            return self.project.compile_pdf_file(tex_path, cwd=self.session.root)
        elif main_file:
            tex_path = self.project.core / main_file
            return self.project.compile_pdf_file(tex_path, cwd=tex_path.parent)
        else:
            return self.project.compile_pdf()

    @staticmethod
    def _format_success(result) -> str:
        rel = result.pdf_path.name if result.pdf_path else "unknown"
        msg = f"Success! PDF generated: {rel} ({result.duration_ms:.0f}ms, method: {result.method})"
        if result.warnings:
            msg += f"\n  {len(result.warnings)} warnings"
        if hasattr(result, '_fix_log') and result._fix_log:
            msg += "\n\nAuto-fix log:"
            for entry in result._fix_log:
                msg += f"\n  - {entry}"
        return msg

    @staticmethod
    def _format_failure(result) -> str:
        msg = f"Compilation Failed (method: {result.method})"
        for e in result.errors[:10]:
            msg += f"\n  {e}"
        if result.log_excerpt:
            msg += f"\n\nLog excerpt:\n{result.log_excerpt[-1500:]}"
        if hasattr(result, '_fix_log') and result._fix_log:
            msg += "\n\nAuto-fix log:"
            for entry in result._fix_log:
                msg += f"\n  - {entry}"
        return msg

    @staticmethod
    def _extract_fixable_warnings(warnings: list) -> list:
        """Filter warnings to only those worth auto-fixing."""
        fixable = []
        for w in warnings:
            for pattern in _FIXABLE_WARNING_PATTERNS:
                if pattern.search(w):
                    fixable.append(w)
                    break
        return fixable

    # ------------------------------------------------------------------
    # Auto-fix: compilation errors
    # ------------------------------------------------------------------

    async def _auto_fix_errors(self, compile_result, main_file, on_token) -> "CompileResult":
        """Iteratively fix compilation errors."""
        fix_log = []
        for round_i in range(1, self.MAX_FIX_ROUNDS + 1):
            if on_token:
                on_token(f"\n🔧 Error fix round {round_i}/{self.MAX_FIX_ROUNDS}...\n")
            logger.info(f"LaTeX error fix round {round_i}: {len(compile_result.errors)} errors")

            error_summary = self._format_failure(compile_result)
            # Also include .log tail for richer context
            log_tail = self._read_log_tail(main_file)
            if log_tail:
                error_summary += f"\n\nFull log tail (last 80 lines):\n{log_tail}"

            fix_result = await self._run_fix_agent(
                _FIX_ERROR_SYSTEM_PROMPT, error_summary, main_file,
                "failed to compile", on_token=on_token
            )
            fix_log.append(f"Error round {round_i}: {fix_result}")

            compile_result = self._do_compile(main_file)
            if compile_result.success:
                compile_result._fix_log = fix_log
                return compile_result

        compile_result._fix_log = fix_log
        return compile_result

    # ------------------------------------------------------------------
    # Auto-fix: content-correctness warnings
    # ------------------------------------------------------------------

    async def _auto_fix_warnings(self, compile_result, fixable_warnings, main_file, on_token):
        """Iteratively fix content-correctness warnings."""
        fix_log = getattr(compile_result, '_fix_log', None) or []
        for round_i in range(1, self.MAX_FIX_ROUNDS + 1):
            if on_token:
                on_token(f"\n🔧 Warning fix round {round_i}/{self.MAX_FIX_ROUNDS}...\n")
            logger.info(f"LaTeX warning fix round {round_i}: {len(fixable_warnings)} fixable warnings")

            warning_summary = "Fixable warnings:\n" + "\n".join(f"  - {w}" for w in fixable_warnings)
            fix_result = await self._run_fix_agent(
                _FIX_WARNING_SYSTEM_PROMPT, warning_summary, main_file,
                "compiled successfully but has warnings", on_token=on_token
            )
            fix_log.append(f"Warning round {round_i}: {fix_result}")

            compile_result = self._do_compile(main_file)
            if not compile_result.success:
                compile_result._fix_log = fix_log
                return compile_result

            fixable_warnings = self._extract_fixable_warnings(compile_result.warnings)
            if not fixable_warnings:
                compile_result._fix_log = fix_log
                return compile_result

        compile_result._fix_log = fix_log
        return compile_result

    # ------------------------------------------------------------------
    # Fix agent: lightweight LLM loop
    # ------------------------------------------------------------------

    async def _run_fix_agent(self, system_prompt: str, issue_summary: str,
                             main_file: Optional[str], issue_type: str,
                             on_token=None) -> str:
        """Run a mini agent loop that reads issues and applies fixes."""
        tex_name = main_file or self.project.config.main_tex

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"The LaTeX file '{tex_name}' {issue_type}. "
                f"Here are the issues:\n\n{issue_summary}\n\n"
                f"Please read the relevant file(s) and fix the issues."
            )},
        ]

        # Allow up to 30 tool-call turns within a single fix round
        max_inner_turns = 3
        for turn_i in range(max_inner_turns):
            if on_token:
                on_token(f"    [llm turn {turn_i+1}] thinking...\n")
            # Enable streaming to avoid long waits (especially for reasoning models)
            _dot_count = [0]
            def _stream_progress(token):
                _dot_count[0] += 1
                if _dot_count[0] % 5 == 0 and on_token:
                    on_token(".")

            try:
                response = await self.provider.chat(
                    messages=messages,
                    tools=_FIX_TOOLS,
                    model=self.model,
                    max_tokens=4096,
                    temperature=0.0,
                    on_token=_stream_progress,
                )
            except Exception as e:
                err_str = str(e).lower()
                if "context_length" in err_str or "too long" in err_str or re.search(r"max.*token", err_str):
                    logger.warning(f"Fix agent context too long, ending this round early.")
                    if on_token:
                        on_token("    [context too long, ending round]\n")
                    return "Context too long, ending round."
                logger.error(f"Fix agent LLM call failed: {e}")
                return f"LLM error: {e}"

            # If no tool calls, the agent is done — return its summary
            if not response.has_tool_calls:
                if on_token and response.content:
                    on_token(f"    [agent] {response.content[:200]}\n")
                return response.content or "No changes made."

            # Log assistant thinking
            if on_token and response.content:
                on_token(f"    [think] {response.content[:150]}\n")

            # Append assistant message
            messages.append({"role": "assistant", "content": response.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                for tc in response.tool_calls
            ]})

            # Execute each tool call
            for tc in response.tool_calls:
                tool_result = self._execute_fix_tool(tc.name, tc.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })
                # Log tool call
                if on_token:
                    args_short = json.dumps(tc.arguments, ensure_ascii=False)
                    if len(args_short) > 120:
                        args_short = args_short[:120] + "..."
                    result_short = tool_result[:100].replace("\n", " ")
                    on_token(f"    [{turn_i+1}] {tc.name}({args_short}) → {result_short}\n")

        return "Fix agent reached max inner turns."

    def _execute_fix_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call from the fix agent."""
        try:
            if tool_name == "read_file":
                return self._fix_read_file(
                    arguments.get("path", ""),
                    arguments.get("start_line"),
                    arguments.get("end_line"),
                )
            elif tool_name == "str_replace":
                return self._fix_str_replace(
                    arguments.get("path", ""),
                    arguments.get("old_string", ""),
                    arguments.get("new_string", ""),
                )
            elif tool_name == "list_files":
                return self._fix_list_files(
                    arguments.get("path", "."),
                )
            else:
                return f"[ERROR] Unknown tool: {tool_name}"
        except Exception as e:
            return f"[ERROR] {e}"

    def _resolve_fix_path(self, path: str) -> Path:
        """Resolve a relative path for the fix agent, respecting Worker overlay."""
        if self.session and hasattr(self.session, '_role_type') and self.session._role_type == "Worker":
            return self.session.resolve(path)
        return self.project.resolve(path)

    def _fix_read_file(self, path: str, start_line: int = None, end_line: int = None) -> str:
        resolved = self._resolve_fix_path(path)
        if not resolved.exists():
            return f"[ERROR] File not found: {path}"
        raw = resolved.read_text(encoding="utf-8")
        lines = raw.splitlines()
        total = len(lines)
        start = max(1, start_line or 1) - 1
        end = min(end_line or total, total)
        numbered = [f"{i+1:>4}| {lines[i]}" for i in range(start, end)]
        content = "\n".join(numbered)
        if start > 0 or end < total:
            content += f"\n[FILE] {path} — lines {start+1}-{end} of {total}"
        else:
            content += f"\n[FILE] {path} — {total} lines"
        return content

    def _fix_str_replace(self, path: str, old_string: str, new_string: str) -> str:
        resolved = self._resolve_fix_path(path)
        if not resolved.exists():
            return f"[ERROR] File not found: {path}"
        content = resolved.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"[ERROR] old_string not found in '{path}'."
        if count > 1:
            return f"[ERROR] old_string found {count} times in '{path}'. Add more context to make it unique."
        new_content = content.replace(old_string, new_string, 1)
        if self.session and hasattr(self.session, '_role_type') and self.session._role_type == "Worker":
            target = self.session.write_target(path)
            target.write_text(new_content, encoding="utf-8")
        else:
            self.project.write_file(path, new_content)
        match_line = content[:content.index(old_string)].count("\n") + 1
        return f"Replaced in {path} at line {match_line}."

    def _fix_list_files(self, path: str) -> str:
        """List files in a directory relative to the project."""
        resolved = self._resolve_fix_path(path)
        if not resolved.exists():
            return f"[ERROR] Directory not found: {path}"
        if not resolved.is_dir():
            return f"[ERROR] Not a directory: {path}"
        entries = []
        for item in sorted(resolved.iterdir()):
            if item.name.startswith('.'):
                continue
            suffix = "/" if item.is_dir() else ""
            entries.append(f"  {item.name}{suffix}")
        if not entries:
            return f"Directory '{path}' is empty."
        return f"Files in '{path}':\n" + "\n".join(entries)

    def _read_log_tail(self, main_file: str = None, max_lines: int = 80) -> str:
        """Read the tail of the .log file for richer error context."""
        tex_name = main_file or self.project.config.main_tex
        stem = Path(tex_name).stem
        if self.session and hasattr(self.session, '_role_type') and self.session._role_type == "Worker":
            log_path = self.session.root / (stem + ".log")
        else:
            log_path = self.project.core / (stem + ".log")
        if not log_path.exists():
            return ""
        try:
            lines = log_path.read_text(errors="replace").splitlines()
            tail = lines[-max_lines:] if len(lines) > max_lines else lines
            return "\n".join(tail)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Fallback: single-pass pdflatex (no project context)
    # ------------------------------------------------------------------

    def _compile_fallback(self, main_file: str) -> str:
        import subprocess

        if self.session:
            try:
                target_path = self.session.resolve(main_file)
            except PermissionError as e:
                return f"[ERROR] {e}"
        elif self.workspace_root:
            target_path = (self.workspace_root / main_file).resolve()
            try:
                target_path.relative_to(self.workspace_root)
            except ValueError:
                return f"[ERROR] Access denied. {main_file} is outside workspace root."
        else:
            return "[ERROR] No workspace or session configured."

        if not target_path.exists():
            return f"[ERROR] File {main_file} not found."

        working_dir = target_path.parent
        engine = self._detect_engine(target_path)
        cmd = [engine, "-interaction=nonstopmode", "-file-line-error", target_path.name]
        logger.info(f"Compiling LaTeX (fallback, engine={engine}): {' '.join(cmd)} in {working_dir}")

        try:
            proc = subprocess.run(cmd, cwd=str(working_dir), capture_output=True, text=True, timeout=60)
            pdf_path = target_path.with_suffix(".pdf")

            if proc.returncode == 0 and pdf_path.exists():
                return f"Success! PDF generated at: {pdf_path.name}"

            log_file = target_path.with_suffix(".log")
            if log_file.exists():
                return f"Compilation Failed.\n\nErrors:\n{self._parse_log(log_file)}"
            return f"Compilation Failed.\nOutput:\n{proc.stdout}\nError:\n{proc.stderr}"
        except subprocess.TimeoutExpired:
            return "[ERROR] Compilation timed out after 60 seconds."
        except FileNotFoundError:
            return "[ERROR] `pdflatex` not found. Please verify TeX Live/MacTeX is installed."
        except Exception as e:
            return f"Unexpected error: {e}"

    @staticmethod
    def _detect_engine(tex_path: Path) -> str:
        """Auto-detect the best LaTeX engine by scanning the first 50 lines."""
        from core.project import Project
        return Project._detect_engine(tex_path)

    @staticmethod
    def _parse_log(log_file: Path) -> str:
        """Extract critical errors from a LaTeX log file."""
        content = log_file.read_text(errors="replace")
        errors = []
        lines = content.splitlines()
        it = iter(lines)
        for line in it:
            if line.startswith("!"):
                msg = line
                try:
                    nxt = next(it)
                    if nxt.strip().startswith("l."):
                        msg += f"\n   Context: {nxt.strip()}"
                except StopIteration:
                    pass
                errors.append(msg)
            elif re.search(r":\d+: ", line):
                errors.append(line)
        if not errors:
            return "No specific error patterns matched. Last 10 lines:\n" + "\n".join(lines[-10:])
        unique = list(dict.fromkeys(errors))
        return "\n".join(unique[:20])

    # ------------------------------------------------------------------
    # Holistic fix: unified LLM-driven self-loop (for task_commit, etc.)
    # ------------------------------------------------------------------

    _HOLISTIC_SYSTEM_PROMPT = """\
You are a LaTeX quality reviewer and fixer. You receive the full compilation log \
(errors AND warnings) and an integrity report showing broken file references.

Your job:
1. **Broken references**: If the report shows \\input/\\includegraphics pointing to \
missing files, comment out or remove those lines so the document is self-consistent.
2. **Compilation issues**: Fix errors, warnings, package conflicts, undefined commands, etc.
3. Ignore harmless noise (font substitution, overfull hbox).
4. After fixing, call `compile` to recompile and check the new log.
5. Repeat until satisfied, then call `done`.

Rules:
- Read files BEFORE editing. Never guess file contents.
- Apply minimal, targeted fixes via str_replace. Do NOT rewrite or restructure content.
- Fix as many issues as possible per turn. Use parallel tool calls.
- Common fixes: package conflicts (duplicate hyperref, cite vs natbib), undefined \
commands (\\citet without natbib), missing \\pgfplotsset{compat}, bad \\ref/\\cite keys.
- For missing files: comment out the referencing line, do NOT fabricate content.
"""

    _HOLISTIC_COMPILE_SCHEMA = {
        "type": "function",
        "function": {
            "name": "compile",
            "description": "Recompile the LaTeX project and return the new compilation log (errors + warnings).",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    _HOLISTIC_DONE_SCHEMA = {
        "type": "function",
        "function": {
            "name": "done",
            "description": (
                "Signal that you are finished reviewing. "
                "verdict='PASS' means the document is acceptable. "
                "Call this when all fixable issues have been addressed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["PASS"],
                        "description": "Always PASS. Call this when done.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief summary of what was fixed and what remains (if anything).",
                    },
                },
                "required": ["verdict", "reason"],
            },
        },
    }

    MAX_HOLISTIC_TURNS = 15

    async def holistic_fix(self, main_file: str = None, on_token=None) -> str:
        """Unified LLM-driven compile-review-fix loop.

        Unlike _auto_fix_errors/_auto_fix_warnings, this hands full control
        to the LLM: it sees the complete log, decides what to fix, recompiles
        when it wants, and calls ``done`` when satisfied.

        Returns a human-readable summary string.
        """
        if not self.project:
            return "[skip] No project context."
        if not self.provider:
            return "[skip] No LLM provider for holistic fix."

        # Check main tex file exists
        tex_name = main_file or self.project.config.main_tex
        tex_path = self.project.core / tex_name
        if not tex_path.exists():
            return "[skip] No main tex file found."

        # Check for broken file references in main.tex
        integrity_report = self._check_deliverables_integrity(tex_name)

        # Initial compile
        result = self._do_compile(main_file)
        compile_summary = self._format_compile_log(result)

        # Skip only if compilation is perfectly clean AND no integrity issues
        if (result.success and not result.errors and not result.warnings
                and not integrity_report):
            return "Compilation clean — no issues found."

        if on_token:
            on_token("\n🔍 Holistic LaTeX review starting...\n")

        tools = [
            _READ_FILE_SCHEMA,
            _STR_REPLACE_SCHEMA,
            _LIST_FILES_SCHEMA,
            self._HOLISTIC_COMPILE_SCHEMA,
            self._HOLISTIC_DONE_SCHEMA,
        ]

        # Build initial context
        user_parts = [
            "The LaTeX project has been compiled. Here is the full result:\n",
            compile_summary,
        ]
        if integrity_report:
            user_parts.append(
                "\n\n--- Deliverables Integrity Report ---\n" + integrity_report
            )
        user_parts.append(
            "\n\nPlease review, fix what you can, and call `done` when satisfied."
        )

        messages = [
            {"role": "system", "content": self._HOLISTIC_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        fix_log = []
        for turn_i in range(self.MAX_HOLISTIC_TURNS):
            if on_token:
                on_token(f"  [turn {turn_i + 1}] thinking...\n")

            try:
                response = await self.provider.chat(
                    messages=messages,
                    tools=tools,
                    model=self.model,
                    max_tokens=4096,
                    temperature=0.0,
                )
            except Exception as e:
                err_str = str(e).lower()
                if "context_length" in err_str or "too long" in err_str:
                    fix_log.append("Context too long, ending early.")
                    break
                logger.error(f"Holistic fix LLM error: {e}")
                fix_log.append(f"LLM error: {e}")
                break

            # No tool calls → agent is done talking
            if not response.has_tool_calls:
                if response.content:
                    fix_log.append(response.content)
                break

            if response.content:
                fix_log.append(response.content)

            # Append assistant message
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id, "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute tool calls
            done_called = False
            for tc in response.tool_calls:
                if tc.name == "done":
                    reason = tc.arguments.get("reason", "")
                    fix_log.append(f"Done: {reason}")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"OK. {reason}"})
                    done_called = True
                elif tc.name == "compile":
                    result = self._do_compile(main_file)
                    compile_summary = self._format_compile_log(result)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": compile_summary})
                    if on_token:
                        e_cnt = len(result.errors) if result.errors else 0
                        w_cnt = len(result.warnings) if result.warnings else 0
                        on_token(f"  [compile] {e_cnt} errors, {w_cnt} warnings\n")
                else:
                    tool_result = self._execute_fix_tool(tc.name, tc.arguments)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
                    if on_token:
                        on_token(f"  [{tc.name}] done\n")

            if done_called:
                break

        summary = "Holistic fix log:\n" + "\n".join(f"  - {entry[:200]}" for entry in fix_log) if fix_log else "No fixes applied."
        if on_token:
            on_token(f"\n✅ Holistic review complete.\n")
        return summary

    @staticmethod
    def _format_compile_log(result) -> str:
        """Format a CompileResult into a full log for the holistic agent."""
        parts = []
        if result.success:
            parts.append("Compilation: SUCCESS (PDF generated)")
        else:
            parts.append("Compilation: FAILED (no PDF or errors)")
        if result.errors:
            parts.append(f"\nErrors ({len(result.errors)}):")
            for e in result.errors[:30]:
                parts.append(f"  {e}")
        if result.warnings:
            parts.append(f"\nWarnings ({len(result.warnings)}):")
            for w in result.warnings[:30]:
                parts.append(f"  {w}")
        if result.log_excerpt:
            parts.append(f"\nLog tail:\n{result.log_excerpt[-2000:]}")
        return "\n".join(parts)

    def _check_deliverables_integrity(self, main_file: str) -> str:
        """Check that all \\input/\\includegraphics in main.tex point to real files.

        Returns a report string, or empty string if everything is fine.
        """
        if not self.project:
            return ""

        core = self.project.core
        tex_path = core / main_file
        if not tex_path.exists():
            return ""

        issues = []
        tex_content = tex_path.read_text(encoding="utf-8", errors="replace")

        ref_patterns = [
            (r'\\input\{([^}]+)\}', "\\input"),
            (r'\\include\{([^}]+)\}', "\\include"),
            (r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', "\\includegraphics"),
        ]
        for pattern, cmd_name in ref_patterns:
            for match in re.finditer(pattern, tex_content):
                ref_path = match.group(1)
                candidates = [core / ref_path]
                if not ref_path.endswith('.tex') and cmd_name in ('\\input', '\\include'):
                    candidates.append(core / (ref_path + '.tex'))
                if not any(c.exists() for c in candidates):
                    issues.append(f"MISSING: {cmd_name}{{{ref_path}}} — file not found in core")

        if not issues:
            return ""
        return "\n".join(issues)
