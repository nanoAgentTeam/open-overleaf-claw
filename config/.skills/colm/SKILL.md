---
name: colm
description: "COLM (Conference on Language Modeling) paper formatting — activate when the user wants COLM template setup, migration, or formatting/compilation fixes."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: COLM PAPER FORMAT]

Activate when: user mentions COLM, Conference on Language Modeling, or asks to use/fix the COLM template.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow `ml-paper-writing` skill.

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: `templates/colm2025/` (referred to as `TEMPLATES_DIR` below), targeting **COLM 2025**.
Contents: `colm2025_conference.sty`, `colm2025_conference.bst`, `colm2025_conference.tex`, `colm2025_conference.bib`, `colm2025_conference.pdf`, `fancyhdr.sty`, `natbib.sty`, `math_commands.tex`.

### Pre-step: Year Confirmation & Template Acquisition

**This step MUST be completed before any scenario below.**

1. Confirm target year and stage (`submission`, `preprint`, or `final`). Default to latest available year if user does not specify.
2. Check whether `TEMPLATES_DIR` exists and includes required files: `colm2025_conference.sty`, `colm2025_conference.bst`, `colm2025_conference.tex`, `fancyhdr.sty`, `natbib.sty`.
3. **Use local built-in template only when BOTH conditions hold**:
   - target year = 2025
   - files in `TEMPLATES_DIR` are complete
4. **If either condition fails** (target year is not 2025 OR local template files are missing/incomplete), execute this workflow:
   - Inform user local built-in template is unavailable or year-mismatched
   - Open official COLM site: http://www.colmweb.org/
   - Find target-year CFP/submission page and locate "Author Kit", "Style Files", or template links
   - If official site has no direct files, check target-year OpenReview submission page for template links
   - Download official target-year template package (`.zip` or repository snapshot)
   - Unzip downloaded files directly into <PROJECT_CORE>.
   - Continue all remaining steps with downloaded year-specific filenames
5. Confirm paper type/page policy from current CFP before edits (common baseline in recent years: main text up to 9 pages, references unlimited).
6. **Filename substitution rule for all steps below**:
   - Treat `colm2025_conference` in commands/examples as a placeholder for the resolved style basename from the selected `.sty` file.
   - Example: if the downloaded file is `colm2026_conference.sty`, replace `colm2025_conference` with `colm2026_conference` in `\\usepackage`, `\\bibliographystyle`, copy commands, and checks.

### Scenario Routing

- User says "create / new COLM paper" → **Scenario 1**
- User says "switch to COLM format" / "apply COLM template" → **Scenario 2**
- User says "COLM format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

### Scenario 1: Create a New COLM Project

**Step 1** — Copy template files to project core directory using `bash`:
```
bash(command="cp TEMPLATES_DIR/colm2025_conference.sty TEMPLATES_DIR/colm2025_conference.bst TEMPLATES_DIR/fancyhdr.sty TEMPLATES_DIR/natbib.sty <PROJECT_CORE>/")
```

**Step 2** — Read `TEMPLATES_DIR/colm2025_conference.tex` with `read_file` for canonical preamble and document structure.

**Step 3** — Create `main.tex` using `write_file`:
- `\documentclass{article}`
- Submission mode by default: `\usepackage[submission]{colm2025_conference}`
- Keep core packages from template (`microtype`, `hyperref`, `url`, `booktabs`, `lineno`)
- Keep line-number block:
  - `\ifcolmsubmission`
  - `\linenumbers`
  - `\fi`
- Use `\bibliography{references}` (or project bib file)
- Use `\bibliographystyle{colm2025_conference}`

**Step 4** — Run `latex_compile`; if errors occur, fix and recompile.

### Scenario 2: Switch an Existing Project to COLM Template

**Step 1** — Read current `main.tex` with `read_file` to analyze current preamble.

**Step 2** — Read `TEMPLATES_DIR/colm2025_conference.tex` with `read_file` as migration reference.

**Step 3** — Copy style files using `bash` (**do NOT overwrite paper content**):
```
bash(command="cp TEMPLATES_DIR/colm2025_conference.sty TEMPLATES_DIR/colm2025_conference.bst TEMPLATES_DIR/fancyhdr.sty TEMPLATES_DIR/natbib.sty <PROJECT_CORE>/")
```

**Step 4** — Update preamble using `str_replace`:
- Set `\documentclass{article}`
- Set mode package per stage:
  - Submission: `\usepackage[submission]{colm2025_conference}`
  - Preprint: `\usepackage[preprint]{colm2025_conference}`
  - Camera-ready: `\usepackage[final]{colm2025_conference}`
- Remove conflicting layout/font overrides (`geometry`, manual margins, external Palatino/Times overrides that conflict with template)

**Step 5** — Align submission/final behavior:
- Submission must keep anonymity and line numbers
- Final mode can expose author information
- Do not include identifying acknowledgements in anonymous submission

**Step 6** — Fix bibliography setup:
- `\bibliographystyle{colm2025_conference}`
- `\bibliography{references}` (or existing bib file)

**Step 7** — Run `latex_compile` and resolve remaining issues.

### Scenario 3: Fix COLM Format Issues

**Step 1** — Run `latex_compile` to capture errors/warnings.

**Step 2** — Read preamble in `main.tex` and compare with `TEMPLATES_DIR/colm2025_conference.tex`.

**Step 3** — Check common COLM failures:
- Missing `colm2025_conference.sty` / `.bst` in project root
- Wrong mode (using `final` or `preprint` during anonymous submission)
- Missing line-number block in submission mode
- Wrong bibliography style (not `colm2025_conference`)
- Manual margin/font overrides that break template geometry

**Step 4** — Apply fixes with `str_replace`.

**Step 5** — Re-run `latex_compile` until clean.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read full `main.tex` with `read_file`.

**Step 2** — Verify checklist items:
- [ ] `\usepackage[submission]{colm2025_conference}` is used for review submission
- [ ] No identifying author info or acknowledgements in anonymous submission
- [ ] Line numbers enabled for submission (`\ifcolmsubmission ... \linenumbers ... \fi`)
- [ ] Main text page count follows current CFP (commonly 9 pages; references unlimited)
- [ ] Paper size/layout not overridden (template targets US Letter, 8.5x11 in)
- [ ] Bibliography uses `colm2025_conference` style
- [ ] Optional sections (ethics statement, appendix) placed after main text according to CFP

**Step 3** — Report and fix issues one by one with `str_replace`.

**Step 4** — Run final `latex_compile` verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: COLM policies can change by year. Always prioritize the target year's CFP and author kit over defaults in this skill.

### Template Download

- COLM website: http://www.colmweb.org/
- Check target-year OpenReview/CFP pages for official author kit links

### Setup: Unzip Location

Unzip into project root (same folder as `main.tex`):
```
project/
├── main.tex
├── colm2025_conference.sty
├── colm2025_conference.bst
├── colm2025_conference.tex
├── fancyhdr.sty
└── natbib.sty
```

### Read These Files First

1. `colm2025_conference.tex` — canonical setup and usage
2. `colm2025_conference.pdf` — formatting instructions
3. `colm2025_conference.sty` — option behavior (`submission`, `preprint`, `final`)

### Template Setup in `main.tex`

```latex
\documentclass{article}
\usepackage[submission]{colm2025_conference}

\usepackage{microtype}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{lineno}

\ifcolmsubmission
\linenumbers
\fi
```

### Key Format Rules

| Item | Requirement |
|------|-------------|
| Submission mode | Use `[submission]` for blind review |
| Layout | Single-column, US Letter dimensions (set by style) |
| Page limit | Typically 9 pages main text + unlimited references (verify CFP) |
| Bibliography | `\bibliographystyle{colm2025_conference}` |
| Camera-ready | Switch to `[final]` only after acceptance |

### Common Pitfalls

- Using wrong mode option for review (`final` instead of `submission`)
- Missing `colm2025_conference.sty` or `.bst` in root
- Overriding margins/fonts with `geometry` or custom hacks
- Forgetting submission line numbers
- Using non-COLM bibliography style
