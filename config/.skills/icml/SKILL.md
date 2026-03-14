---
name: icml
description: "ICML (International Conference on Machine Learning) paper formatting — activate when the user wants to submit to ICML, follow ICML template, or fix ICML format issues."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: ICML PAPER FORMAT]

Activate when: user mentions ICML, International Conference on Machine Learning, or asks to use the ICML template.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow `ml-paper-writing` skill.

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: `templates/icml2026/` (referred to as `TEMPLATES_DIR` below), targeting **ICML 2026**.
Contents: `icml2026.sty`, `icml2026.bst`, `example_paper.tex`, `fancyhdr.sty`, `algorithm.sty`, `algorithmic.sty`.

### Pre-step: Year Confirmation & Template Acquisition

**This step MUST be completed before any scenario below.**

1. Confirm the target year with the user (default: latest available year).
2. Check whether `TEMPLATES_DIR` exists and includes required files: `icml2026.sty`, `icml2026.bst`, `example_paper.tex`, `fancyhdr.sty`, `algorithm.sty`, `algorithmic.sty`.
3. **Use local built-in template only when BOTH conditions hold**:
   - target year = 2026
   - files in `TEMPLATES_DIR` are complete
4. **If either condition fails** (target year is not 2026 OR local template files are missing/incomplete):
   - Inform the user local built-in template is unavailable or year-mismatched.
   - Guide the user to download the correct Author Kit from:
     - Official website: https://icml.cc → target year → "Author Instructions" or "Submission Guidelines" → download Style Files `.zip`
     - Overleaf fallback: search "ICML [year]" on https://www.overleaf.com/latex/templates
   - Unzip downloaded files directly into <PROJECT_CORE>.
   - All subsequent steps must use downloaded year-specific filenames (e.g., `icml2025.sty`).
5. **Filename substitution rule for all steps below**:
   - Treat `icml2026` in commands/examples as a placeholder for the resolved package basename from the selected `.sty` file.
   - Example: if the downloaded file is `icml2025.sty`, replace `icml2026` with `icml2025` everywhere (`\\usepackage`, `.bst`, copy commands, checklist checks).

### Scenario Routing

- User says "create / new ICML paper" → **Scenario 1**
- User says "switch to ICML format" / "apply ICML template" → **Scenario 2**
- User says "ICML format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

### Scenario 1: Create a New ICML Project

**Step 1** — Copy template files to the project core directory using `bash`:
```
bash(command="cp TEMPLATES_DIR/icml2026.sty TEMPLATES_DIR/icml2026.bst TEMPLATES_DIR/fancyhdr.sty TEMPLATES_DIR/algorithm.sty TEMPLATES_DIR/algorithmic.sty <PROJECT_CORE>/")
```

**Step 2** — Read `TEMPLATES_DIR/example_paper.tex` with `read_file` to understand the preamble structure and required macros.

**Step 3** — Create `main.tex` in the project core directory using `write_file`:
- Keep the template preamble (`\documentclass{article}` + `\usepackage[submitted]{icml2026}`)
- Replace body content with the user's paper content or generate a skeleton (title / abstract / sections)
- Set `\bibliographystyle{icml2026}` and `\bibliography{references}`

**Step 4** — Run `latex_compile` to verify successful compilation. If it fails, read the log and fix errors.

### Scenario 2: Switch an Existing Project to ICML Template

**Step 1** — Read the current `main.tex` with `read_file` to analyze the existing preamble and content structure.

**Step 2** — Read `TEMPLATES_DIR/example_paper.tex` with `read_file` to understand the required ICML preamble.

**Step 3** — Copy style files to the project core directory using `bash` (**style files only — do NOT overwrite user content**):
```
bash(command="cp TEMPLATES_DIR/icml2026.sty TEMPLATES_DIR/icml2026.bst TEMPLATES_DIR/fancyhdr.sty TEMPLATES_DIR/algorithm.sty TEMPLATES_DIR/algorithmic.sty <PROJECT_CORE>/")
```

**Step 4** — Modify the `main.tex` preamble using `str_replace`:
- Change `\documentclass` to `\documentclass{article}`
- Add `\usepackage[submitted]{icml2026}`
- Remove packages that conflict with ICML (`geometry`, `multicol`, standalone font packages, etc.)

**Step 5** — Adjust ICML-specific macros:
- Set `\icmltitle{}` for the paper title
- Set `\icmltitlerunning{}` for the running title (submission phase)
- Ensure the author block is empty during the submission phase

**Step 6** — Set up bibliography:
- `\bibliographystyle{icml2026}`
- `\bibliography{references}`

**Step 7** — Run `latex_compile` to verify successful compilation. If it fails, read the error log and fix.

### Scenario 3: Fix ICML Format Issues

**Step 1** — Run `latex_compile` on the current project to obtain error/warning messages.

**Step 2** — Read the preamble of `main.tex` with `read_file`.

**Step 3** — Cross-check against the "Common Pitfalls" and "Key Format Rules" sections below. Common causes:
- Missing `icml2026.sty` or `fancyhdr.sty`
- Using the `geometry` package to override margins
- Using `\onecolumn` or `multicol` which breaks the two-column layout
- `\bibliographystyle` not set to `icml2026`

**Step 4** — Fix the issues using `str_replace`.

**Step 5** — Run `latex_compile` to verify the fix.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read the full `main.tex` with `read_file`.

**Step 2** — Check each item:
- [ ] **Anonymization**: `[submitted]` option is used; no author information present
- [ ] **Page limit**: body ≤ 8 pages (excluding references) — verify against the current year's CFP
- [ ] **Two-column layout**: no `\onecolumn` or `geometry` usage
- [ ] **Bibliography style**: uses `icml2026` bst
- [ ] **Forbidden packages**: no `geometry`, `multicol`, or standalone font packages

**Step 3** — Report any issues found and fix them one by one using `str_replace`.

**Step 4** — Run `latex_compile` for final compilation verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: The rules below reflect common patterns from recent years. Conference requirements (page limits, required sections, package restrictions, submission options, etc.) **can change each year**. Before making any formatting changes, verify all requirements against the **current year's official CFP** and the **author kit files** (sample `.tex`, README, formatting guide PDF) bundled in the template download.

---

### Template Download

**Official source** (URL changes each year):
- Go to https://icml.cc → current year → "Author Instructions" or "Submission Guidelines"
- Download the "Style Files" or "Author Kit" `.zip`

**Overleaf**:
- Search "ICML [year] Example Paper" on https://www.overleaf.com/latex/templates

**CTAN** (if TeX Live / MiKTeX is installed):
```
tlmgr install icml
```

---

### Setup: Unzip Location

Unzip into the **project root** (same directory as `main.tex`):
```
project/
├── main.tex
├── icml2026.sty          ← style file, must be at root
├── example_paper.tex     ← sample paper — READ THIS
└── icml2026.bst          ← bibliography style
```

---

### Read These Files First

1. **`example_paper.tex`** — canonical reference for every format element; read it before editing `main.tex`
2. Comments inside `icml2026.sty` — explains option flags

---

### Template Setup in `main.tex`

ICML uses **`article` document class + `.sty` package**:

```latex
\documentclass{article}

% Choose ONE option:
\usepackage[submitted]{icml2026}   % anonymous blind review (use for submission)
% \usepackage[accepted]{icml2026}  % camera-ready after acceptance
% \usepackage{icml2026}            % no header/footer (draft/preprint)
```

**Rule**: Use `[submitted]` for anonymous review. Switch to `[accepted]` only for camera-ready.

---

### Key Format Rules

| Item | Requirement |
|------|-------------|
| Page limit | Typically **8 pages** content + unlimited references — verify at https://icml.cc current year CFP |
| Layout | **Two-column** (enforced by style) |
| Font size | 10pt |
| Anonymous | Remove all author info for `[submitted]` option |
| Appendix | Typically does not count toward page limit — verify at current year CFP |

---

### Common Pitfalls

- **Do NOT change column layout** — the `.sty` enforces two-column; using `\onecolumn` or `multicol` breaks the template.
- **`\icmltitle{}`** takes the paper title; `\icmlauthor{}{}` takes name + affiliation. For submission, use `\icmltitlerunning{}` only and omit authors.
- **Page limit**: always verify with the current year's CFP — page counts and appendix rules change between years.
- **Do NOT use `geometry` package** to override margins — the style sets margins; overriding causes page-size issues.
- `fancyhdr.sty` is a dependency; if it's missing, install with `tlmgr install fancyhdr`.

---

### Bibliography

ICML uses standard BibTeX (not natbib):
```latex
\bibliographystyle{icml2026}   % matches the .bst file in the author kit
\bibliography{references}
```
Use the `icml2026.bst` file that comes with the author kit. Do NOT use `plain`, `abbrv`, or `unsrtnat`.

---

### Author Block (camera-ready only)

```latex
\icmlauthor{Author Name}{affil1}
\icmlaffiliation{affil1}{Department, University, City, Country}
\icmlcorrespondingauthor{Author Name}{email@example.com}
```
See `example_paper.tex` for the full author block pattern.
