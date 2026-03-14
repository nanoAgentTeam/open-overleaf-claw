---
name: iclr
description: "ICLR (International Conference on Learning Representations) paper formatting — activate when the user wants to submit to ICLR, follow ICLR template, or fix ICLR format issues."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: ICLR PAPER FORMAT]

Activate when: user mentions ICLR, International Conference on Learning Representations, or asks to use the ICLR template.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow `ml-paper-writing` skill.

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: `templates/iclr2026/` (referred to as `TEMPLATES_DIR` below), targeting **ICLR 2026**.
Contents: `iclr2026_conference.sty`, `iclr2026_conference.bst`, `iclr2026_conference.tex`, `iclr2026_conference.bib`, `math_commands.tex`, `fancyhdr.sty`, `natbib.sty`.

### Pre-step: Year Confirmation & Template Acquisition

**This step MUST be completed before any scenario below.**

1. Confirm the target year with the user (default: latest available year).
2. Check whether `TEMPLATES_DIR` exists and includes required files: `iclr2026_conference.sty`, `iclr2026_conference.bst`, `iclr2026_conference.tex`, `math_commands.tex`, `fancyhdr.sty`, `natbib.sty`.
3. **Use local built-in template only when BOTH conditions hold**:
   - target year = 2026
   - files in `TEMPLATES_DIR` are complete
4. **If either condition fails** (target year is not 2026 OR local template files are missing/incomplete):
   - Inform the user local built-in template is unavailable or year-mismatched.
   - Guide the user to download the correct Author Kit from:
     - Official website: https://iclr.cc → target year → "Author Guidelines" or "Submission Instructions"
     - OpenReview: template link on the target-year submission page
     - Overleaf fallback: search "ICLR [year] Conference Paper Template" on https://www.overleaf.com/latex/templates
   - Unzip downloaded files directly into <PROJECT_CORE>.
   - All subsequent steps must use the downloaded year-specific filenames (e.g., `iclr2025_conference.sty`).
5. **Filename substitution rule for all steps below**:
   - Treat `iclr2026_conference` in commands/examples as a placeholder for the resolved style basename from the selected `.sty` file.
   - Example: if the downloaded file is `iclr2025_conference.sty`, replace `iclr2026_conference` with `iclr2025_conference` everywhere (`\\usepackage`, `\\bibliographystyle`, copy commands, checklist checks).

### Scenario Routing

- User says "create / new ICLR paper" → **Scenario 1**
- User says "switch to ICLR format" / "apply ICLR template" → **Scenario 2**
- User says "ICLR format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

### Scenario 1: Create a New ICLR Project

**Step 1** — Copy template files to the project core directory using `bash`:
```
bash(command="cp TEMPLATES_DIR/iclr2026_conference.sty TEMPLATES_DIR/iclr2026_conference.bst TEMPLATES_DIR/math_commands.tex TEMPLATES_DIR/fancyhdr.sty TEMPLATES_DIR/natbib.sty <PROJECT_CORE>/")
```

**Step 2** — Read `TEMPLATES_DIR/iclr2026_conference.tex` with `read_file` to understand the preamble structure, author block pattern, and required macros.

**Step 3** — Create `main.tex` in the project core directory using `write_file`:
- Preamble: `\documentclass{article}` + `\usepackage{iclr2026_conference,times}`
- Load `hyperref` and `url` AFTER the style package
- Do NOT add `\iclrfinalcopy` (submission must be anonymous)
- Set `\author{Anonymous Author(s)}` for submission
- Replace body content with the user's paper content or generate a skeleton (title / abstract / sections)
- Set `\bibliographystyle{iclr2026_conference}` and `\bibliography{references}`

**Step 4** — Run `latex_compile` to verify successful compilation. If it fails, read the log and fix errors.

### Scenario 2: Switch an Existing Project to ICLR Template

**Step 1** — Read the current `main.tex` with `read_file` to analyze the existing preamble and content structure.

**Step 2** — Read `TEMPLATES_DIR/iclr2026_conference.tex` with `read_file` to understand the required ICLR preamble.

**Step 3** — Copy style files to the project core directory using `bash` (**style files only — do NOT overwrite user content**):
```
bash(command="cp TEMPLATES_DIR/iclr2026_conference.sty TEMPLATES_DIR/iclr2026_conference.bst TEMPLATES_DIR/fancyhdr.sty TEMPLATES_DIR/natbib.sty <PROJECT_CORE>/")
```

**Step 4** — Modify the `main.tex` preamble using `str_replace`:
- Change `\documentclass` to `\documentclass{article}`
- Add `\usepackage{iclr2026_conference,times}`
- Ensure `hyperref` is loaded AFTER `iclr2026_conference` (loading order matters)
- Remove packages that conflict with ICLR (`geometry`, standalone font packages other than `times`, etc.)
- Do NOT add `\iclrfinalcopy`

**Step 5** — Adjust ICLR-specific elements:
- Set `\title{}` for the paper title
- Set `\author{Anonymous Author(s)}` for submission phase
- Ensure `\iclrfinalcopy` is NOT present (or is commented out)

**Step 6** — Set up bibliography:
- `\bibliographystyle{iclr2026_conference}`
- `\bibliography{references}`
- Do NOT use `plain`, `abbrv`, or `natbib` styles

**Step 7** — Run `latex_compile` to verify successful compilation. If it fails, read the error log and fix.

### Scenario 3: Fix ICLR Format Issues

**Step 1** — Run `latex_compile` on the current project to obtain error/warning messages.

**Step 2** — Read the preamble of `main.tex` with `read_file`.

**Step 3** — Cross-check against the "Common Pitfalls" and "Key Format Rules" sections below. Common causes:
- Missing `iclr2026_conference.sty` or `.bst` in the project root
- `hyperref` loaded BEFORE `iclr2026_conference` (causes option clash)
- Missing `times` package (font falls back to Computer Modern)
- `\iclrfinalcopy` accidentally left active during submission
- Using `geometry` to override margins

**Step 4** — Fix the issues using `str_replace`.

**Step 5** — Run `latex_compile` to verify the fix.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read the full `main.tex` with `read_file`.

**Step 2** — Check each item:
- [ ] **Anonymization**: `\iclrfinalcopy` is NOT present or is commented out; `\author{Anonymous Author(s)}`
- [ ] **Page limit**: body ≤ 9 pages (excluding references) — verify against the current year's CFP
- [ ] **Single-column layout**: no layout overrides
- [ ] **Font**: `times` package is loaded
- [ ] **Bibliography style**: uses `iclr2026_conference` bst
- [ ] **hyperref loading order**: loaded AFTER `iclr2026_conference`
- [ ] **Forbidden packages**: no `geometry` or conflicting font packages

**Step 3** — Report any issues found and fix them one by one using `str_replace`.

**Step 4** — Run `latex_compile` for final compilation verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: The rules below reflect common patterns from recent years. Conference requirements (page limits, required sections, package restrictions, submission options, etc.) **can change each year**. Before making any formatting changes, verify all requirements against the **current year's official CFP** and the **author kit files** (sample `.tex`, README, formatting guide PDF) bundled in the template download.

---

### Template Download

**Official source**:
- Go to https://iclr.cc → current year → "Author Guidelines" or "Submission Instructions"
- The template is also linked from the OpenReview submission page for the current year

**Overleaf**:
- Search "ICLR [year] Conference Paper Template" on https://www.overleaf.com/latex/templates
- The official ICLR Overleaf template is maintained by the organizers

**GitHub** (most reliable for latest version):
- Search GitHub for `iclr-conference/iclr-paper-template` or similar

---

### Setup: Unzip Location

Unzip into the **project root** (same directory as `main.tex`):
```
project/
├── main.tex
├── iclr2026_conference.sty    ← style file, must be at root
├── iclr2026_conference.bst    ← bibliography style, must be at root
└── iclr2026_conference.tex    ← sample paper — READ THIS
```

---

### Read These Files First

1. **`iclr2026_conference.tex`** — the sample paper; contains preamble setup, author block, abstract, and section examples with explanatory comments
2. Comments inside `iclr2026_conference.sty` — explains `\iclrfinalcopy` and other options

---

### Template Setup in `main.tex`

ICLR uses **`article` document class + multiple packages** (no single all-in-one `.sty`):

```latex
\documentclass{article}

\usepackage{iclr2026_conference, times}
\usepackage{hyperref}
\usepackage{url}

% For camera-ready ONLY (de-anonymizes the paper):
% \iclrfinalcopy
```

**Rule**: Do NOT add `\iclrfinalcopy` for submission. Add it only after acceptance for camera-ready.

---

### Key Format Rules

| Item | Requirement |
|------|-------------|
| Page limit | Typically **9 pages** content + unlimited references — verify at https://iclr.cc current year CFP |
| Layout | **Single column** |
| Font | Times (loaded by `times` package) |
| Anonymous | No `\iclrfinalcopy` at submission; author block replaced with `\author{Anonymous Author(s)}` |
| Appendix | Typically unlimited after references — verify at current year CFP |

---

### Author Block

**Submission (anonymous)**:
```latex
\author{Anonymous Author(s)}
```

**Camera-ready** (after adding `\iclrfinalcopy`):
```latex
\author{%
  First Author\thanks{Equal contribution.} \\
  Department, University \\
  City, Country \\
  \texttt{email@example.com} \\
  \And
  Second Author \\
  Department, University \\
  \texttt{email2@example.com}
}
```

---

### Common Pitfalls

- **`\iclrfinalcopy` must be placed BEFORE `\begin{document}`** — placing it inside the document body has no effect.
- **Do NOT use `geometry` package** — margins are set by the style.
- **`hyperref` must be loaded AFTER `iclr2026_conference`** — loading order matters; the style file configures hyperref internally.
- **`times` package is required** — do not omit it; without it the font falls back to Computer Modern, which violates format requirements.
- If `.sty` or `.bst` not found: both must be in the project root.

---

### Bibliography

ICLR uses a custom `.bst` file (bundled in the author kit):
```latex
\bibliographystyle{iclr2026_conference}
\bibliography{references}
```
Do NOT use `plain`, `abbrv`, or `natbib` styles — the `iclr2026_conference.bst` produces the required citation format.
