---
name: paper-research-form
description: |
  Generate structured CSV literature survey tables. MUST activate this skill (instead of plain-text replies) when the user requests a literature review, paper collection, related work survey, or comparison of papers on a topic.
  生成结构化 CSV 文献调研表格。当用户要求调研论文、收集文献、整理相关工作、对比论文时，必须激活此 skill 生成 CSV 输出，而非纯文字回复。
  Triggers: survey, related work, literature review, paper list, find papers, collect papers, compare papers, 调研, 文献, 找论文, 相关论文, 收集论文, 整理文献, 论文列表, 帮我找论文.
  Output: multi-source search → metadata extraction → 8-column CSV (title, abstract, summary, relevance, authors, year, venue, link) → send to IM.
allowed-tools:
  - web_search
  - web_fetch
  - read_file
  - write_file
  - send_file
---
[SKILL: PAPER RESEARCH FORM — CSV LITERATURE SURVEY]

## Output Schema

Generate a CSV file with these 8 columns (in order — content first, metadata second):

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | title | str | Full paper title |
| 2 | abstract_snippet | str | First 200 chars of abstract, ending with "..." |
| 3 | summary | str | 1-2 sentence summary of key contribution, written by you |
| 4 | relevance | enum | High / Medium / Low — relevance to the user's research topic |
| 5 | authors | str | First author et al. (e.g. "Zhang et al.") |
| 6 | year | int | Publication year |
| 7 | venue | str | Conference or journal name (e.g. NeurIPS 2024, TACL) |
| 8 | link | url | Canonical URL: prefer Semantic Scholar > arXiv > ACL Anthology > DOI |

## Workflow

### 1. Clarify Scope

Ask user (if not already specified):
- Research topic / keywords
- Target venues or "any"
- Year range (default: last 3 years)
- How many papers (default: 10-15)

### 2. Search Strategy

Use `conference-research` skill search patterns when targeting specific venues.

General search order:
1. `web_search: site:semanticscholar.org "{topic}" {year range}` — broad coverage
2. `web_search: site:arxiv.org "{topic}" {year}` — preprints
3. `web_search: site:aclanthology.org "{topic}" {year}` — NLP venues
4. `web_search: site:openreview.net {topic keywords} {venue} {year}` — ML venues

For each promising result, use `web_fetch` to get full metadata (title, authors, abstract, venue, year).

### 3. Populate Table

For each paper found:
- Extract metadata accurately — never fabricate authors, years, or venues
- Write abstract_snippet: first 200 characters of the real abstract + "..."
- Write summary: 1-2 sentences capturing the core contribution in your own words
- Assess relevance: High (directly addresses the topic), Medium (related method/task), Low (tangentially relevant)

### 4. Write CSV

- Sort by relevance (High first), then by year (newest first)
- **Append by default**: Look for existing `survey_*.csv` files in the project directory. Match by topic slug in filename (e.g. searching "RAG" → match `survey_rag_*.csv`). If a matching file is found, append new results to it (skip duplicates by matching title). If multiple matches exist, pick the most recently modified one. Only create a new file when no match is found or user explicitly requests a new survey direction.
- **File naming**: New files use `survey_{topic_slug}_{YYYYMMDD}.csv` (e.g. `survey_rag_20260326.csv`). Use user-specified path if provided.
- **Encoding**: Always prepend UTF-8 BOM (`\xef\xbb\xbf`) so Excel displays Chinese correctly.
- Use `write_file` tool with CSV content
- Use proper CSV escaping: double-quote fields containing commas or newlines

### 5. Send to IM

- Call `send_file` with the CSV file path and a brief caption summarizing the survey (e.g. "文献调研: {topic}, 共 {N} 篇, {H} 篇高相关").
- If `send_file` fails, inform the user the file is saved locally and provide the path.

### 6. Report

After writing CSV, present a markdown summary to the user:
- Total papers found
- Breakdown by relevance: N High / N Medium / N Low
- Top 3 most relevant papers with 1-line descriptions
- Note any gaps or suggested follow-up searches

## Quality Rules

- **Never hallucinate papers.** Every entry must come from a verified search result with a working link.
- **Never guess metadata.** If author/year/venue is unclear from search results, use `web_fetch` to verify or mark as "Unknown".
- **Deduplicate.** If the same paper appears in multiple sources (arXiv + conference), keep only the published venue version.
- **Minimum quality bar.** Only include papers with clear abstracts and identifiable venues. Skip workshop papers unless specifically requested.
