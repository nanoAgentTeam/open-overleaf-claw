"""Research profile builder for TeX-heavy projects.

Uses LLM to extract structured research profile from TeX content.
Falls back to regex-based extraction when no LLM provider is available.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from loguru import logger


class TexResearchProfileBuilder:
    """Extract research profile from TeX files, optionally using LLM."""

    name = "research_core"

    def __init__(self, provider: Optional[Any] = None, model: Optional[str] = None):
        self._provider = provider
        self._model = model

    # ------------------------------------------------------------------
    # Public API (sync, matches ProfileBuilder protocol)
    # ------------------------------------------------------------------

    def build(self, project: Any) -> dict[str, Any]:
        tex_snippets = self._collect_tex_snippets(project)
        source_files = self._list_source_files(project)

        if self._provider and tex_snippets.strip():
            try:
                result = self._run_async(self._llm_extract(project, tex_snippets, source_files))
                if result:
                    return result
            except Exception as e:
                logger.warning(f"LLM profile extraction failed, falling back to regex: {e}")

        return self._regex_extract(project, tex_snippets, source_files)

    # ------------------------------------------------------------------
    # Tex content collection
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_tex_snippets(project: Any) -> str:
        """Collect meaningful text from tex files for LLM analysis."""
        core = project.core
        tex_files = sorted(core.rglob("*.tex"))

        parts: list[str] = []

        for tex in tex_files[:10]:
            try:
                raw = tex.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Keep first 50 lines raw (has template info, packages, comments)
            header_lines = raw.splitlines()[:50]
            parts.append(f"=== {tex.name} (header) ===\n" + "\n".join(header_lines))

            # Extract abstract and introduction content (strip LaTeX noise)
            abstract = _extract_section(raw, "abstract")
            intro = _extract_section(raw, "introduction")
            if abstract:
                parts.append(f"=== {tex.name} (abstract) ===\n" + abstract[:1500])
            if intro:
                parts.append(f"=== {tex.name} (introduction) ===\n" + intro[:1500])

        # Cap total size
        joined = "\n\n".join(parts)
        return joined[:6000]

    @staticmethod
    def _list_source_files(project: Any) -> list[str]:
        core = project.core
        return [f.name for f in sorted(core.rglob("*.tex"))[:10]]

    # ------------------------------------------------------------------
    # LLM extraction
    # ------------------------------------------------------------------

    async def _llm_extract(
        self, project: Any, tex_snippets: str, source_files: list[str]
    ) -> Optional[dict[str, Any]]:
        prompt = (
            "根据以下 LaTeX 论文片段，提取论文的研究画像。输出严格的 JSON（不要 markdown 包裹）。\n\n"
            "要求提取：\n"
            "- topic: 一句话描述论文研究主题（中文或英文均可，取决于论文语言）\n"
            "- keywords: 5-10 个核心关键词（英文，学术检索用）\n"
            "- stage: 论文当前阶段，从以下选一个：ideation / writing / experiment / revision / submission\n"
            "- target_venue: 目标投稿会议或期刊（从模板、样式文件、注释中推断；若无法判断则为 null）\n"
            "- venue_confidence: 对 target_venue 的置信度：high（模板明确指定）/ medium（从内容推断）/ low（猜测）/ null\n"
            "- summary: 2-3 句话概括论文核心贡献和方法\n\n"
            "注意：\n"
            "- 如果内容全是模板占位符（如 'Your Name', 'Example Paper'），topic 写 'template_placeholder'，keywords 为空列表\n"
            "- target_venue 从 documentclass、usepackage、sty 文件名、注释中推断"
            "（如 aaai2026.sty → 'AAAI 2026'，neurips_2026 → 'NeurIPS 2026'）\n\n"
            f"论文片段：\n{tex_snippets}\n\n"
            "JSON 输出："
        )

        response = await self._provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
        )

        if not response or not response.content:
            return None

        parsed = _parse_json_response(response.content)
        if not parsed or not isinstance(parsed, dict):
            return None

        # Normalize and validate
        topic = str(parsed.get("topic", "")).strip()
        if not topic or topic == "template_placeholder":
            topic = project.id.replace("_", " ")

        keywords = parsed.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()][:15]

        stage = str(parsed.get("stage", "writing")).strip().lower()
        if stage not in ("ideation", "writing", "experiment", "revision", "submission"):
            stage = "writing"

        target_venue = parsed.get("target_venue")
        if target_venue:
            target_venue = str(target_venue).strip() or None

        venue_confidence = parsed.get("venue_confidence")
        if venue_confidence:
            venue_confidence = str(venue_confidence).strip().lower() or None

        summary = str(parsed.get("summary", "")).strip() or None

        return {
            "project_id": project.id,
            "topic": topic,
            "keywords": keywords,
            "stage": stage,
            "target_venue": target_venue,
            "venue_confidence": venue_confidence,
            "summary": summary,
            "source_files": source_files,
            "extraction_method": "llm",
            "updated_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Regex fallback (original logic, improved stop words)
    # ------------------------------------------------------------------

    @staticmethod
    def _regex_extract(
        project: Any, tex_snippets: str, source_files: list[str]
    ) -> dict[str, Any]:
        # Strip LaTeX commands for word frequency
        cleaned = re.sub(r"===.*===", " ", tex_snippets)
        cleaned = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", cleaned)
        cleaned = re.sub(r"[%].*$", " ", cleaned, flags=re.MULTILINE)

        words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{3,}", cleaned.lower())
        stop = {
            "this", "that", "with", "from", "using", "paper", "method", "results",
            "table", "figure", "section", "approach", "model", "models", "data",
            "experiments", "introduction", "related", "work", "conclusion",
            "your", "second", "first", "third", "author", "affiliation", "example",
            "abstract", "include", "should", "would", "could", "which", "their",
            "these", "those", "there", "here", "where", "when", "than", "then",
            "other", "each", "such", "also", "been", "have", "more", "most",
            "some", "only", "over", "into", "between", "through", "based",
            "proposed", "propose", "show", "shows", "shown", "used", "given",
            "different", "following", "however", "specific", "number", "text",
            "letterpaper", "article", "usepackage", "documentclass",
            "name", "email", "institute", "university", "department",
            "contributions", "contribution", "discuss", "point", "summarize",
        }
        keywords = [w for w, _ in Counter(w for w in words if w not in stop).most_common(15)]

        stage = "writing"
        lowered = cleaned.lower()
        if "deadline" in lowered or "submission" in lowered:
            stage = "submission"
        elif "experiment" in lowered:
            stage = "experiment"

        topic = project.id.replace("_", " ")
        if keywords:
            topic = f"{keywords[0]} / {keywords[1]}" if len(keywords) > 1 else keywords[0]

        # Try to detect venue from template
        target_venue = None
        venue_match = re.search(
            r"(?:aaai|neurips|icml|iclr|cvpr|eccv|acl|emnlp|naacl|ijcai|kdd|www|sigir)"
            r"[\s_\-]*(\d{4})",
            tex_snippets.lower(),
        )
        if venue_match:
            target_venue = venue_match.group(0).replace("_", " ").replace("-", " ").upper().strip()

        return {
            "project_id": project.id,
            "topic": topic,
            "keywords": keywords,
            "stage": stage,
            "target_venue": target_venue,
            "venue_confidence": "high" if target_venue else None,
            "summary": None,
            "source_files": source_files,
            "extraction_method": "regex",
            "updated_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_async(coro):
        """Run an async coroutine from sync context."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=60)
        else:
            return asyncio.run(coro)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _extract_section(tex: str, section_name: str) -> Optional[str]:
    """Extract text content of a section from raw LaTeX."""
    # Match \begin{abstract}...\end{abstract} or \section{Introduction}...\section{...}
    if section_name == "abstract":
        m = re.search(
            r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
            tex, re.DOTALL,
        )
        if m:
            return _strip_latex(m.group(1))

    pattern = rf"\\section\*?\{{{section_name}\}}(.*?)(?=\\section\*?\{{|\\end\{{document\}}|$)"
    m = re.search(pattern, tex, re.DOTALL | re.IGNORECASE)
    if m:
        return _strip_latex(m.group(1))

    return None


def _strip_latex(text: str) -> str:
    """Rough strip of LaTeX commands, keep readable text."""
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"[%].*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    # Remove markdown code block wrapping
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None
