---
name: neurips
description: "NeurIPS (Neural Information Processing Systems) paper formatting — activate when the user wants to submit to NeurIPS, follow NeurIPS template, or fix NeurIPS format issues."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: NeurIPS PAPER FORMAT]

Activate when: user mentions NeurIPS, Neural Information Processing Systems, or asks to use the NeurIPS template.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow `ml-paper-writing` skill.

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: `templates/neurips2025/` (referred to as `TEMPLATES_DIR` below), targeting **NeurIPS 2025**.
Contents: `neurips.sty`, `main.tex`, `extra_pkgs.tex`, `Makefile`.

### Pre-step: Year Confirmation & Template Acquisition

**This step MUST be completed before any scenario below.**

1. Confirm the target year with the user (default: latest available year).
2. Check whether `TEMPLATES_DIR` exists and includes required files: `neurips.sty`, `main.tex`, `extra_pkgs.tex`.
3. **Use local built-in template only when BOTH conditions hold**:
   - target year = 2025
   - files in `TEMPLATES_DIR` are complete
4. **If either condition fails** (target year is not 2025 OR local template files are missing/incomplete):
   - Inform the user local built-in template is unavailable or year-mismatched.
   - Guide the user to download the correct Author Kit from:
     - Official website: https://neurips.cc → "Conferences" → target year → "Call for Papers" or "Author Instructions" → download Style Files `.zip`
     - Overleaf fallback: search "NeurIPS [year]" on https://www.overleaf.com/latex/templates
   - Unzip downloaded files directly into <PROJECT_CORE>.
   - All subsequent steps must use downloaded year-specific filenames.
5. **Filename substitution rule for all steps below**:
   - Resolve the package name from the selected `.sty` filename (basename without `.sty`).
   - Treat `neurips` in commands/examples as a placeholder for that resolved package name.
   - Example: if the selected style file is `neurips_2025.sty`, replace `neurips` with `neurips_2025` in `\\usepackage`, copy commands, and related checks.

### Scenario Routing

- User says "create / new NeurIPS paper" → **Scenario 1**
- User says "switch to NeurIPS format" / "apply NeurIPS template" → **Scenario 2**
- User says "NeurIPS format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

### Scenario 1: Create a New NeurIPS Project

**Step 1** — Copy template files to the project core directory using `bash`:
```
bash(command="cp TEMPLATES_DIR/neurips.sty TEMPLATES_DIR/extra_pkgs.tex <PROJECT_CORE>/")
```

**Step 2** — Read `TEMPLATES_DIR/main.tex` with `read_file` to understand the preamble structure and required macros.

**Step 3** — Create `main.tex` in the project core directory using `write_file`:
- Keep the template preamble (`\documentclass{article}` + `\usepackage{neurips}`)
- Use NO option for anonymous submission (default); use `[final]` only for camera-ready
- If using natbib separately, add `[nonatbib]` option and load natbib manually
- Replace body content with the user's paper content or generate a skeleton (title / abstract / sections)
- Set `\bibliographystyle{abbrvnat}` and `\bibliography{references}`

**Step 4** — Run `latex_compile` to verify successful compilation. If it fails, read the log and fix errors.

### Scenario 2: Switch an Existing Project to NeurIPS Template

**Step 1** — Read the current `main.tex` with `read_file` to analyze the existing preamble and content structure.

**Step 2** — Read `TEMPLATES_DIR/main.tex` with `read_file` to understand the required NeurIPS preamble.

**Step 3** — Copy style files to the project core directory using `bash` (**style files only — do NOT overwrite user content**):
```
bash(command="cp TEMPLATES_DIR/neurips.sty <PROJECT_CORE>/")
```

**Step 4** — Modify the `main.tex` preamble using `str_replace`:
- Change `\documentclass` to `\documentclass{article}`
- Add `\usepackage{neurips}` (no option = anonymous submission)
- Remove packages that conflict with NeurIPS (`geometry`, `times`, `mathptmx`, standalone font packages, etc.)
- Do NOT remove `\usepackage[utf8]{inputenc}` — it is required

**Step 5** — Adjust NeurIPS-specific elements:
- Set `\title{}` for the paper title
- Set `\author{Anonymous Author(s)}` for submission phase
- Ensure no identifying information is present

**Step 6** — Set up bibliography:
- `\bibliographystyle{abbrvnat}` (or `unsrtnat`, `plainnat`)
- `\bibliography{references}`
- If using `[nonatbib]` option, use a standard `.bst` style instead

**Step 7** — Run `latex_compile` to verify successful compilation. If it fails, read the error log and fix.

### Scenario 3: Fix NeurIPS Format Issues

**Step 1** — Run `latex_compile` on the current project to obtain error/warning messages.

**Step 2** — Read the preamble of `main.tex` with `read_file`.

**Step 3** — Cross-check against the "Common Pitfalls" and "Key Format Rules" sections below. Common causes:
- Missing `neurips.sty` in the project root
- Using `\usepackage{times}` or `\usepackage{mathptmx}` separately (NeurIPS loads fonts internally)
- Using the `geometry` package to override margins
- `\author{}` not set to anonymous for submission

**Step 4** — Fix the issues using `str_replace`.

**Step 5** — Run `latex_compile` to verify the fix.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read the full `main.tex` with `read_file`.

**Step 2** — Check each item:
- [ ] **Anonymization**: no option (anonymous) is used; `\author{Anonymous Author(s)}`
- [ ] **Page limit**: body ≤ 9 pages (excluding references) — verify against the current year's CFP
- [ ] **Single-column layout**: no layout overrides
- [ ] **Bibliography style**: uses `abbrvnat` or another natbib-compatible style
- [ ] **Forbidden packages**: no `geometry`, `times`, `mathptmx`
- [ ] **Checklist**: `neurips_XXXX_checklist.md` is filled out and appended after references

**Step 3** — Report any issues found and fix them one by one using `str_replace`.

**Step 4** — Run `latex_compile` for final compilation verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: The rules below reflect common patterns from recent years. Conference requirements (page limits, required sections, package restrictions, submission options, etc.) **can change each year**. Before making any formatting changes, verify all requirements against the **current year's official CFP** and the **author kit files** (sample `.tex`, README, formatting guide PDF) bundled in the template download.

---

### Template Download

**Official source** (URL changes each year — always fetch the current year's):
- Go to https://neurips.cc → "Conferences" → current year → "Call for Papers" or "Author Instructions"
- Look for "Style Files" or "LaTeX Style Files" download link (usually a `.zip`)

**Overleaf** (no local install needed):
- Search "NeurIPS [year]" on https://www.overleaf.com/latex/templates
- Select the official NeurIPS template and clone it

**CTAN** (if TeX Live is installed):
```
tlmgr install neurips
```

---

### Setup: Unzip Location

Unzip the author kit into the **project root** (same directory as `main.tex`):
```
project/
├── main.tex
├── neurips.sty             ← style file, must be at root
├── extra_pkgs.tex          ← additional package imports
└── Makefile                ← build helper
```
The `.sty` file must be alongside `main.tex` so LaTeX can find it without a path prefix.

---

### Read These Files First

Before editing, always read these in order:
1. **`main.tex`** — the sample paper; contains preamble setup and document structure
2. **`extra_pkgs.tex`** — additional packages used by the template
3. Comments inside `neurips.sty` (last resort; the sample .tex is usually sufficient)

---

### Template Setup in `main.tex`

NeurIPS uses **`article` document class + a `.sty` package** (NOT a custom `.cls`):

```latex
\documentclass{article}

% Choose ONE option:
\usepackage{neurips}                    % anonymous submission (default for review)
% \usepackage[final]{neurips}           % camera-ready (de-anonymizes, adds copyright)
% \usepackage[preprint]{neurips}        % arXiv preprint (no "Submitted to..." notice)
% \usepackage[nonatbib]{neurips}        % if you manage bibliography without natbib
```

**Rule**: Submit with NO option (anonymous). Switch to `[final]` only for camera-ready.

---

### Key Format Rules

| Item | Requirement |
|------|-------------|
| Page limit | Typically **9 pages** content + unlimited references — verify at https://neurips.cc current year CFP |
| Layout | **Single column** |
| Font | Times-like (handled by style; do not override font packages) |
| Anonymous | Author names/affiliations must be removed for submission |
| Checklist | Reproducibility/ethics checklist must be included as an appendix |
| Appendix | Unlimited pages; placed after references |

---

### Common Pitfalls

- **Do NOT use `\usepackage{times}` or `\usepackage{mathptmx}` separately** — the NeurIPS style loads fonts internally; adding them causes conflicts.
- **Do NOT remove `\usepackage[utf8]{inputenc}`** — required for special characters.
- **`\author{}`** must be `\author{Anonymous Author(s)}` during submission. Forget this = desk rejection.
- **Margin overrides are forbidden** — do not use `geometry` to change margins.
- If `neurips.sty` is not found at compile time: the file is missing from the project root. Download the template and place the `.sty` there.

---

### Bibliography

NeurIPS uses **natbib** by default:
```latex
\bibliographystyle{abbrvnat}   % or unsrtnat, plainnat
\bibliography{references}
```
If you used `[nonatbib]`, use a standard `.bst` style instead.

---

### Checklist (Submission Requirement)

The ethics/reproducibility checklist (`neurips_XXXX_checklist.md`) must be filled out and appended after the references. The sample `.tex` shows exactly where to include it.
