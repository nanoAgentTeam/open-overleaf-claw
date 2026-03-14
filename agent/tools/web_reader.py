"""Tool for reading web content (PDFs via pymupdf4llm, HTML via Jina Reader)."""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pymupdf4llm
import requests
from loguru import logger

# Cache directory for downloaded files (original PDFs, etc.)
_CACHE_DIR = Path.home() / ".context_bot" / "cache" / "papers"


class WebReaderTool:
    """
    Tool to read web content.
    - specialized in converting PDFs to Markdown using pymupdf4llm (preserving layout, tables).
    - converts standard web pages to Markdown using Jina Reader.
    """
    name = "web_fetch"
    description = (
        "Fetch and read the content of a URL. "
        "Specialized for converting PDFs (via pymupdf4llm) and Web Pages to clean Markdown. "
        "For PDFs, the original file is cached locally and can be sent to the user via send_file."
    )

    def __init__(self, session: Any = None, workspace: Any = None, config: Any | None = None, **kwargs):
        from config.schema import Config
        self.session = session
        self.workspace = Path(workspace) if workspace else None
        self.config = config or Config()

    def to_schema(self) -> dict:
        return self.to_openai_schema()

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch (PDF or Web Page)."
                        }
                    },
                    "required": ["url"]
                }
            }
        }

    def execute(self, url: str, **kwargs) -> str:
        """Execute the fetch."""
        try:
            logger.info("Fetching URL: %s", url)

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()

            # Handle PDF
            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                logger.info("Detected PDF content, using pymupdf4llm...")
                return self._process_pdf(response.content, url)

            # Handle HTML (using Jina Reader)
            logger.info("Detected HTML content, using Jina Reader...")
            jina_url = "https://r.jina.ai/%s" % url
            jina_response = requests.get(jina_url, timeout=30)
            if jina_response.status_code == 200:
                text = jina_response.text
                MAX_CHARS = 100000
                if len(text) > MAX_CHARS:
                    return (
                        "%s\n\n"
                        "... [CONTENT TRUNCATED] (Original length: %d chars). "
                        "Content exceeded %d characters limit."
                        % (text[:MAX_CHARS], len(text), MAX_CHARS)
                    )
                return text
            else:
                return "Failed to convert HTML to Markdown via Jina Reader. Raw Status: %d" % jina_response.status_code

        except Exception as e:
            return "Error fetching URL: %s" % str(e)

    def _process_pdf(self, pdf_content: bytes, url: str) -> str:
        """Process PDF content using pymupdf4llm.

        1. Cache the original PDF to ~/.context_bot/cache/papers/ for send_file.
        2. Convert to markdown and return in output (no markdown file saved).
        """
        try:
            # Determine a sensible filename from the URL
            filename = url.rstrip("/").split("/")[-1].split("?")[0]
            if not filename.endswith(".pdf"):
                filename = "document.pdf"

            # 1. Cache original PDF
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached_pdf = _CACHE_DIR / filename
            cached_pdf.write_bytes(pdf_content)
            logger.info("Cached original PDF: %s", cached_pdf)

            # 2. Convert to markdown via pymupdf4llm
            # pymupdf4llm needs a file path; reuse the cached file
            md_text = pymupdf4llm.to_markdown(str(cached_pdf))

            # Split content into pages (heuristic based on '-----')
            pages = md_text.split("\n-----\n")
            total_pages = len(pages)

            # Header with original PDF path for agent to use with send_file
            header = (
                "✅ PDF downloaded and cached: `%s`\n"
                "   ↳ Use `send_file` with this path to send the original PDF to the user.\n"
                "📊 Total Pages: %d\n"
                % (str(cached_pdf), total_pages)
            )

            preview_pages = 10
            if total_pages > preview_pages:
                preview_content = "\n-----\n".join(pages[:preview_pages])
                return (
                    "%s"
                    "👀 Showing first %d pages below.\n\n"
                    "---\n\n%s\n\n"
                    "--- (End of Preview, %d more pages) ---"
                    % (header, preview_pages, preview_content, total_pages - preview_pages)
                )
            else:
                return "%s\n---\n\n%s" % (header, md_text)

        except Exception as e:
            return "Error processing PDF with pymupdf4llm: %s" % str(e)
