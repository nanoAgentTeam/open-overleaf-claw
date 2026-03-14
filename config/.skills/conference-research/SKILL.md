---
name: conference-research
description: "Academic venue paper discovery — activate when you need to find papers accepted at specific conferences or journals (ACL, EMNLP, NeurIPS, ICML, ICLR, MLSys, etc.), analyze venue acceptance preferences, or look up CFP requirements."
allowed-tools:
  - web_search
  - web_fetch
  - read_file
---
[SKILL: CONFERENCE RESEARCH PROTOCOL]

When researching papers from specific academic venues, standard `arxiv_search` with venue names WILL FAIL — conference names never appear in arXiv paper titles. Use the source-specific strategies below instead.

## Source Priority (try in order)

### 1. NLP Venues: ACL / EMNLP / NAACL / EACL / COLING
ACL Anthology is the authoritative proceedings database for all ACL-family venues.

```
web_search: site:aclanthology.org "{topic}" {year}
web_search: site:aclanthology.org "{year}.{venue-code}-main"
```

Venue codes: `acl-long`, `acl-short`, `emnlp-main`, `naacl-main`, `eacl-main`

Examples:
- EMNLP 2024 long-document papers → `site:aclanthology.org "long document" 2024.emnlp-main`
- ACL 2023 RAG papers → `site:aclanthology.org "retrieval augmented" 2023.acl-long`

### 2. ML Venues: NeurIPS / ICLR / ICML
All three now use OpenReview. Do NOT use `site:proceedings.mlr.press` — it is not well-indexed by web search.
Do NOT quote the topic phrase; use bare keywords:

```
web_search: site:openreview.net {topic keywords} NeurIPS 2024
web_search: site:openreview.net {topic keywords} ICLR 2024
web_search: site:openreview.net {topic keywords} ICML 2024
```

Examples:
- NeurIPS 2024 long context papers → `site:openreview.net long context NeurIPS 2024`
- ICLR 2025 RAG papers → `site:openreview.net retrieval augmented generation ICLR 2025`

### 3. Systems Venues: MLSys / OSDI / SOSP / EuroSys
Use DBLP:

```
web_search: site:dblp.org {venue-abbrev} {year} {topic keywords}
```

If DBLP returns no results, fall back to a plain web search:
```
web_search: {venue} {year} {topic keywords} accepted papers
```

### 4. Cross-Venue Search via Semantic Scholar
```
web_search: site:semanticscholar.org "{topic}" venue:"{Conference Full Name}"
```

### 5. CFP and Acceptance Criteria
To find Call for Papers, review criteria, or scope descriptions:
```
web_search: "{Conference} {year} call for papers"
web_search: "{Conference} {year} submission guidelines"
web_search: "{Conference} {year} review criteria"
web_search: "{Conference} {year} acceptance rate topics"
```

## Critical Anti-Patterns (NEVER do these)
- ❌ `arxiv_search` with `ti:"ACL"` or `ti:"EMNLP"` — conference names are not in arXiv paper titles
- ❌ Using `arxiv_search` alone to find venue-specific accepted papers
- ❌ Asserting conference preferences based on openalex metadata alone without cross-checking content
- ❌ Treating ACL Findings / Workshop as equivalent to Main Conference acceptance

## Analysis Workflow (after collecting papers)
1. Note each paper's track (Main / Findings / Workshop) — do not conflate them
2. Group papers by methodological approach, not just topic keyword
3. Extract style signals from abstracts and method sections (theoretical vs empirical, task breadth vs depth)
4. Require ≥ 3 papers as evidence before stating a venue preference pattern
5. Cross-validate CFP scope text against the collected paper sample
