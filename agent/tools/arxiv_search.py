from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import threading
import time
import arxiv
from core.tools.base import BaseTool

_SEMAPHORE = threading.Semaphore(2)  # max 2 concurrent arxiv_search requests

# Shared client — _last_request_dt persists across calls so delay_seconds is
# actually enforced. Guarded by _CLIENT_LOCK for thread-safe access.
_CLIENT_LOCK = threading.Lock()
_CLIENT = arxiv.Client(delay_seconds=3.0, num_retries=3)


class ArxivSearchTool(BaseTool):
    """Search for papers on arXiv with filtering, sorting, and pagination."""

    def __init__(self, config: Any = None):
        from config.schema import Config
        self.config = config or Config()

    @property
    def name(self) -> str:
        return "arxiv_search"

    @property
    def description(self) -> str:
        return (
            "Search for research papers on arXiv. Supports keyword search, "
            "field-specific queries (ti: title, abs: abstract, au: author, cat: category), "
            "date filtering, category filtering, sort order, and pagination."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. Supports arXiv field prefixes: "
                        "ti:\"sparse attention\" for title, abs:flash for abstract, "
                        "au:Vaswani for author, cat:cs.LG for category. "
                        "Combine with AND/OR/ANDNOT."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return (default: 10, max: 25).",
                    "default": 10,
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["relevance", "date", "updated"],
                    "description": (
                        "Sort order: 'relevance' (default), 'date' (newest submitted first), "
                        "'updated' (recently updated first)."
                    ),
                    "default": "relevance",
                },
                "date_from": {
                    "type": "string",
                    "description": (
                        "Filter papers submitted on or after this date (YYYY-MM-DD). "
                        "Useful for tracking recent work, e.g. '2024-01-01'."
                    ),
                },
                "date_to": {
                    "type": "string",
                    "description": "Filter papers submitted on or before this date (YYYY-MM-DD).",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Filter by arXiv categories (e.g. ['cs.LG', 'cs.AI', 'cs.CV']). "
                        "Papers must belong to at least one of these categories."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N results (for pagination). Default: 0.",
                    "default": 0,
                },
                "id_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Fetch specific papers by arXiv ID (e.g. ['2307.09288', '2410.12345']). "
                        "When provided, query is ignored."
                    ),
                },
            },
            "required": ["query"],
        }

    def execute(
        self,
        query: str = "",
        max_results: int = 10,
        sort_by: str = "relevance",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        categories: Optional[List[str]] = None,
        offset: int = 0,
        id_list: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        with _SEMAPHORE:
            return self._execute(
                query=query, max_results=max_results, sort_by=sort_by,
                date_from=date_from, date_to=date_to, categories=categories,
                offset=offset, id_list=id_list, **kwargs,
            )

    def _execute(
        self,
        query: str = "",
        max_results: int = 10,
        sort_by: str = "relevance",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        categories: Optional[List[str]] = None,
        offset: int = 0,
        id_list: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        max_results = min(max_results, 25)

        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "date": arxiv.SortCriterion.SubmittedDate,
            "updated": arxiv.SortCriterion.LastUpdatedDate,
        }
        criterion = sort_map.get(sort_by, arxiv.SortCriterion.Relevance)

        # Parse date filters
        dt_from = None
        dt_to = None
        try:
            if date_from:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if date_to:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as e:
            return f"Error: invalid date format ({e}). Use YYYY-MM-DD."

        # Outer retry: if arXiv rate-limits us (429), wait and retry.
        _OUTER_RETRIES = 2
        _OUTER_WAIT_S = 20  # seconds to wait on 429 before outer retry

        papers = []
        for _attempt in range(_OUTER_RETRIES + 1):
            try:
                if id_list:
                    search = arxiv.Search(id_list=id_list, max_results=len(id_list))
                else:
                    # Fetch extra to account for post-filter losses from date/category
                    fetch_n = max_results * 4 + offset if (dt_from or dt_to or categories) else max_results + offset
                    fetch_n = min(fetch_n, 200)
                    search = arxiv.Search(
                        query=query,
                        max_results=fetch_n,
                        sort_by=criterion,
                    )

                # Serialize HTTP calls through the shared client so delay_seconds
                # is respected and _last_request_dt doesn't race between threads.
                with _CLIENT_LOCK:
                    fetched = list(_CLIENT.results(search))

                papers = []
                seen = 0
                for paper in fetched:
                    # Date filter
                    if dt_from and paper.published < dt_from:
                        if sort_by == "date":
                            break  # sorted newest-first, no point continuing
                        continue
                    if dt_to and paper.published > dt_to:
                        continue

                    # Category filter
                    if categories:
                        paper_cats = set(paper.categories)
                        if not paper_cats.intersection(set(categories)):
                            continue

                    seen += 1
                    if seen <= offset:
                        continue

                    papers.append(paper)
                    if len(papers) >= max_results:
                        break

                break  # success — exit retry loop

            except Exception as e:
                err_str = str(e)
                if "429" in err_str and _attempt < _OUTER_RETRIES:
                    time.sleep(_OUTER_WAIT_S)
                    continue
                return f"Error searching arXiv: {err_str}"

        if not papers:
            hints = []
            if dt_from or dt_to:
                hints.append(f"date range {date_from or ''}–{date_to or ''}")
            if categories:
                hints.append(f"categories {categories}")
            hint_str = f" with filters ({', '.join(hints)})" if hints else ""
            return f"No papers found on arXiv matching '{query}'{hint_str}."

        lines = [
            f"arXiv Search Results — query: \"{query}\"  "
            f"sort: {sort_by}  results: {len(papers)}"
            + (f"  offset: {offset}" if offset else "")
            + (f"  date: {date_from or ''}–{date_to or ''}" if (date_from or date_to) else "")
            + (f"  categories: {categories}" if categories else ""),
            "=" * 60,
        ]

        for i, paper in enumerate(papers, 1):
            arxiv_id = paper.entry_id.split("/abs/")[-1]
            authors = [a.name for a in paper.authors]
            author_str = ", ".join(authors[:5])
            if len(authors) > 5:
                author_str += f" ... (+{len(authors) - 5} more)"

            cats = ", ".join(paper.categories[:5])

            entry = [
                f"[{i}] {paper.title}",
                f"    arXiv ID : {arxiv_id}",
                f"    Published: {paper.published.strftime('%Y-%m-%d')}",
            ]
            if paper.updated.date() != paper.published.date():
                entry.append(f"    Updated  : {paper.updated.strftime('%Y-%m-%d')}")
            entry += [
                f"    Authors  : {author_str}",
                f"    Categories: {cats}",
                f"    URL      : {paper.entry_id}",
                f"    PDF      : https://arxiv.org/pdf/{arxiv_id}",
            ]
            if paper.journal_ref:
                entry.append(f"    Journal  : {paper.journal_ref}")
            if paper.comment:
                entry.append(f"    Comment  : {paper.comment[:200]}")
            entry += [
                f"    Abstract : {paper.summary.replace(chr(10), ' ')}",
            ]
            lines.append("\n".join(entry))

        return "\n\n---\n\n".join(lines)
