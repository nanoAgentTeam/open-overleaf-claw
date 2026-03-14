---
name: aaai
description: "AAAI paper formatting — activate when the user wants AAAI template setup, migration, or formatting/compilation fixes."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: AAAI PAPER FORMAT]

Activate when: user mentions AAAI, Association for the Advancement of Artificial Intelligence, or asks to use/fix AAAI template format.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow `ml-paper-writing` skill.

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: `templates/aaai2026/` (referred to as `TEMPLATES_DIR` below), targeting **AAAI 2026**.
Contents: `aaai2026.sty`, `aaai2026.bst`, `aaai2026-unified-template.tex`, `aaai2026-unified-supp.tex`, `aaai2026.bib`.

### Pre-step: Year Confirmation & Author Kit Selection

**This step MUST be completed before any scenario below.**

1. Confirm target year and stage (anonymous submission vs camera-ready/final). Default to latest available year if user does not specify.
2. Check whether `TEMPLATES_DIR` exists and includes required files: `aaai2026.sty`, `aaai2026.bst`, `aaai2026-unified-template.tex`, `aaai2026.bib`.
3. **Use local built-in template only when BOTH conditions hold**:
   - target year = 2026
   - files in `TEMPLATES_DIR` are complete
4. **If either condition fails** (target year is not 2026 OR local template files are missing/incomplete), execute this workflow:
   - Inform user local built-in template is unavailable or year-mismatched
   - Go to https://aaai.org/
   - Navigate: `Conferences` -> target year conference page (for example, AAAI-27)
   - Open "Author Kit" or "Submission Instructions" and download official LaTeX style package
   - If the official page is unavailable/delayed, use Overleaf fallback and search "AAAI <year>"
   - Unzip downloaded files directly into <PROJECT_CORE>.
   - Continue all remaining scenarios with downloaded year-specific filenames
5. Confirm target track/page policy from current CFP before final checks.
6. **Filename substitution rule for all steps below**:
   - Treat `aaai2026` in commands/examples as a placeholder for the resolved package basename from the selected `.sty` file.
   - Example: if the downloaded file is `aaai2025.sty`, replace `aaai2026` with `aaai2025` everywhere (`\\usepackage`, `.bst`, copy commands, checklist checks).

### Scenario Routing

- User says "create / new AAAI paper" → **Scenario 1**
- User says "switch to AAAI format" / "apply AAAI template" → **Scenario 2**
- User says "AAAI format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

### Scenario 1: Create a New AAAI Project

**Step 1** — Copy style files to project core directory using `bash`:
```
bash(command="cp TEMPLATES_DIR/aaai2026.sty TEMPLATES_DIR/aaai2026.bst TEMPLATES_DIR/aaai2026.bib <PROJECT_CORE>/")
```

**Step 2** — Read `TEMPLATES_DIR/aaai2026-unified-template.tex` with `read_file` to follow the official preamble and author/affiliation structure.

**Step 3** — Create `main.tex` using `write_file`:
- `\documentclass[letterpaper]{article}`
- Anonymous submission: `\usepackage[submission]{aaai2026}`
- Camera-ready/final: `\usepackage{aaai2026}`
- Keep required package set from template (`times`, `helvet`, `courier`, `url`, `graphicx`, `natbib`, `caption`)
- Use AAAI author macros: `\author{...}` + `\affiliations{...}`
- Add `\bibliography{references}` (or project bib file)
- **Do not add `\bibliographystyle{aaai2026}` manually** if `natbib` is loaded, because style file sets it automatically

**Step 4** — Run `latex_compile` and fix compile errors.

### Scenario 2: Switch an Existing Project to AAAI Template

**Step 1** — Read current `main.tex` with `read_file`.

**Step 2** — Read `TEMPLATES_DIR/aaai2026-unified-template.tex` with `read_file` as migration baseline.

**Step 3** — Copy style files with `bash` (**style files only — do NOT overwrite paper content**):
```
bash(command="cp TEMPLATES_DIR/aaai2026.sty TEMPLATES_DIR/aaai2026.bst <PROJECT_CORE>/")
```

**Step 4** — Update preamble via `str_replace`:
- Set `\documentclass[letterpaper]{article}`
- Set `\usepackage[submission]{aaai2026}` for review or `\usepackage{aaai2026}` for final
- Keep required AAAI packages and ordering from official template
- Remove forbidden/conflicting packages (especially `hyperref`, `fontenc`, `geometry`, `authblk`, `multicol`)

**Step 5** — Align anonymity/final metadata:
- Submission: anonymize author identity and remove identifying acknowledgements/links
- Final: restore full author + affiliation info and required copyright notice behavior

**Step 6** — Bibliography setup:
- Keep `natbib` loaded
- Use `\bibliography{references}`
- Avoid duplicate `\bibliographystyle{...}` commands

**Step 7** — Run `latex_compile` and resolve remaining issues.

### Scenario 3: Fix AAAI Format Issues

**Step 1** — Run `latex_compile` to collect current errors.

**Step 2** — Read current preamble and compare to `TEMPLATES_DIR/aaai2026-unified-template.tex`.

**Step 3** — Check common AAAI failures:
- Missing `aaai2026.sty` in project root
- Using wrong mode (`\usepackage{aaai2026}` during anonymous submission)
- Loading forbidden packages (`hyperref`, `fontenc`, `geometry`, etc.)
- Duplicate `\bibliographystyle` command causing BibTeX style conflicts
- Using non-AAAI author macro layout (missing `\affiliations{}`)

**Step 4** — Apply targeted fixes via `str_replace`.

**Step 5** — Re-run `latex_compile` until clean.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read full `main.tex` with `read_file`.

**Step 2** — Verify checklist items:
- [ ] `\documentclass[letterpaper]{article}` is used
- [ ] Submission mode uses `\usepackage[submission]{aaai2026}`
- [ ] Anonymous version has no identifying author/affiliation content
- [ ] No forbidden packages/commands (especially `hyperref`, `fontenc`, `geometry`, layout hacks)
- [ ] Two-column layout preserved (do not force custom page geometry)
- [ ] Bibliography setup is valid with AAAI style (`natbib` + no duplicate bibstyle declarations)
- [ ] Page limit matches current CFP/track rules (commonly strict content-page limits)

**Step 3** — Report violations and fix them one by one using `str_replace`.

**Step 4** — Run final `latex_compile` verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: AAAI policies can change by year and track. Always use the target year's CFP + Author Kit as source of truth.

### Template Download

- AAAI conference pages (Author Kit links are year-specific): https://aaai.org/
- Official template examples can also be used in Overleaf if they match target year

### Setup: Unzip Location

Unzip into project root (same folder as `main.tex`):
```
project/
├── main.tex
├── aaai2026.sty
├── aaai2026.bst
├── aaai2026.bib
└── aaai2026-unified-template.tex
```

### Read These Files First

1. `aaai2026-unified-template.tex` — canonical preamble and usage examples
2. `aaai2026.sty` — allowed/forbidden package behavior and submission option rules
3. Target-year CFP or author instructions PDF — page limits and track-specific policies

### Template Setup in `main.tex`

```latex
\documentclass[letterpaper]{article}
\usepackage[submission]{aaai2026} % anonymous review
% \usepackage{aaai2026}           % camera-ready

\usepackage{times}
\usepackage{helvet}
\usepackage{courier}
\usepackage[hyphens]{url}
\usepackage{graphicx}
\usepackage{natbib}
\usepackage{caption}
```

### Key Format Rules

| Item | Requirement |
|------|-------------|
| Paper size | US Letter (8.5x11 in) |
| Layout | Two-column (set by style) |
| Anonymous submission | Use `[submission]` and remove identifying info |
| Forbidden packages | `hyperref`, `fontenc`, `geometry`, and other disallowed packages |
| Bibliography | Use AAAI BibTeX setup; avoid duplicate `\bibliographystyle` declarations |

### Common Pitfalls

- Loading `hyperref` (hard error in AAAI style)
- Mixing non-AAAI author block patterns with AAAI macros
- Keeping author identities in anonymous submission
- Adding `\bibliographystyle{aaai2026}` again when style already sets it
- Using layout/margin hacks that violate template constraints
