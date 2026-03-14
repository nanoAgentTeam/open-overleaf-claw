---
name: conference-tracking
description: "会议录用结果跟踪与趋势分析 — 当用户想追踪主流学术会议（ICLR/ICML/NeurIPS/AAAI/ACL等）的录用情况、分析录用趋势、或结合自身项目获取投稿建议时激活。"
allowed-tools:
  - web_search
  - web_fetch
  - read_file
  - memory_nav
  - memory_list
  - memory_get
  - memory_write
---
[SKILL: CONFERENCE TRACKING PROTOCOL]

Activate when: user asks to track conference results, analyze acceptance trends, 会议跟踪, 会议录用, 录用结果分析, or wants submission advice based on conference patterns.

## Execution Protocol

### Step 1 — Check Memory for Previously Tracked Conferences
Call `memory_nav(domain='job')` to find previous tracking records under scope `job:radar.conference.track`.
Read recent entries (via `memory_list` then `memory_get`) to determine:
- Which conferences have already been tracked and when
- What was the analysis cutoff date for each conference

### Step 2 — Discover New Conference Results
Search for conferences that have published **new** acceptance results since the last tracking.
Use `web_search` with queries like:
- "ICLR 2026 accepted papers announced"
- "NeurIPS 2025 accepted papers list"
Focus only on conferences where results are NEW (not yet in memory).

### Step 3 — Fetch the Official Full Paper List (mandatory)
For each conference with new results:
1. Navigate to the **official accepted papers page** — e.g.:
   - OpenReview: `openreview.net/group?id=ICLR.cc/YEAR/Conference`
   - Virtual site: `conference.cc/virtual/YEAR/papers.html`
   - Proceedings: `proceedings.mlr.press/vXXX/` (ICML), `papers.nips.cc/paper_files/paper/YEAR` (NeurIPS)
2. Use `web_fetch` on the official URL to retrieve the full paper list.
3. **Do NOT fall back to arxiv keyword search as a substitute for the official list.** The goal is the complete, official acceptance record — not a keyword-filtered subset.
4. If the page is too large, fetch the proceedings index or category listing pages.

### Step 4 — Analyze Overall Trends from the Full List
From the complete paper list, identify:
- **Top directions** by paper count (cluster similar titles by topic)
- **Emerging topics** (strong presence this year vs. previous years)
- **Methodology signals** (theoretical vs empirical, large-scale vs efficient, benchmark types)
- **Acceptance rate context** (if available: total submissions vs acceptances)

### Step 5 — Project-Relevant Subset Analysis
Using the project's research topic (extracted in Phase 1/2 of the radar protocol):
- Filter the full list for papers in the same or adjacent research area
- Identify papers directly competitive with or complementary to the project
- Note what properties the accepted papers in this area share (what seems to be rewarded)

### Step 6 — Actionable Recommendations for the Project
Provide specific, evidence-based advice:
- **Target venue**: which conference best fits, based on acceptance trends
- **Strengthen**: what to add or emphasize based on what reviewers seem to reward
- **Mitigate risks**: what weaknesses to address based on apparent rejection signals
- **Competitive positioning**: how to differentiate from accepted papers in the same area

### Step 7 — Record Execution in Memory
Call `memory_write` at the end:
- `kind`: `"job_run"`
- `scope`: `"job:radar.conference.track"`
- `intent`: `"job_progress"`
- `ttl`: `"90d"`
- Content must include: which conferences were checked, which had new results, brief trend summary, date of this execution
