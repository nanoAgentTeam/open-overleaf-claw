---
name: cvpr-iccv-eccv
description: "CVPR / ICCV / ECCV paper formatting — activate when the user wants to submit to CVPR, ICCV, or ECCV, follow their template, or fix format issues for these computer vision conferences."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: CVPR / ICCV / ECCV PAPER FORMAT]

Activate when: user mentions CVPR, ICCV, ECCV, Computer Vision and Pattern Recognition, International Conference on Computer Vision, or European Conference on Computer Vision.

> ⚠️ **Reference only — always verify**: The rules below reflect common patterns from recent years. Conference requirements (page limits, required sections, package restrictions, submission options, etc.) **can change each year**. Before making any formatting changes, verify all requirements against the **current year's official CFP** and the **author kit files** (sample `.tex`, README, formatting guide PDF) bundled in the template download.

> **Note**: CVPR and ICCV share nearly identical templates (both use IEEE CVPR-style). ECCV uses a different Springer LNCS-based template. Instructions are split below — **read the section matching the target venue**.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow:
- `config/.skills/ml-paper-writing/SKILL.md`

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: None — this skill does not bundle templates. Templates must always be downloaded from official sources (see Template Download below).

### Pre-step: Year Confirmation & Template Acquisition

**This step MUST be completed before any scenario below.**

1. Confirm the target year and venue (CVPR, ICCV, or ECCV) with the user. Default to latest available year if user does not specify.
2. Confirm the stage: `submission` (blind review) or `camera-ready` (final).
3. **Download the official template** — this skill has no built-in template; always download from:
   - **CVPR**: https://cvpr.thecvf.com → "Author Guidelines" or "Paper Submission" → download Author Kit `.zip`
   - **ICCV**: https://iccv.thecvf.com → "Author Guidelines" → download Author Kit `.zip`
   - **ECCV**: https://eccv.ecva.net → "Author Guidelines" → download from the ECCV site or https://www.springer.com/gp/computer-science/lncs/conference-proceedings-guidelines
   - **Overleaf fallback**: search the venue name on https://www.overleaf.com/latex/templates
4. Unzip downloaded files directly into <PROJECT_CORE>.
5. Read the sample `.tex` file from the downloaded kit to confirm preamble structure, package requirements, and author block format.
6. Confirm page limit and supplementary material policy from the current year's CFP.

### Scenario Routing

- User says "create / new CVPR/ICCV/ECCV paper" → **Scenario 1**
- User says "switch to CVPR/ICCV/ECCV format" / "apply template" → **Scenario 2**
- User says "format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

### Scenario 1: Create a New Project

**Step 1** — Download and copy template files to project core directory (see Pre-step).

**Step 2** — Read the sample `.tex` from the downloaded kit with `read_file`:
- CVPR/ICCV: `egpaper_for_review.tex` (submission) or `egpaper_final.tex` (camera-ready)
- ECCV: `samplepaper.tex`

**Step 3** — Create `main.tex` using `write_file`:

For **CVPR/ICCV**:
- `\documentclass[10pt,twocolumn,letterpaper]{article}`
- `\usepackage{cvpr}` (or `\usepackage{iccv}` for ICCV)
- Keep `\cvprfinalcopy` commented out for submission
- Set `\def\cvprPaperID{****}` with submission system paper ID
- Do NOT add `\usepackage{hyperref}` (style loads it internally)

For **ECCV**:
- `\documentclass[runningheads]{llncs}`
- Use `\author{}` + `\institute{}` (LNCS syntax)

**Step 4** — Set up bibliography and run `latex_compile`.

### Scenario 2: Switch an Existing Project to CV Venue Template

**Step 1** — Read current `main.tex` with `read_file`.

**Step 2** — Read the downloaded sample `.tex` with `read_file` as migration reference.

**Step 3** — Copy style files using `bash` (**style files only — do NOT overwrite paper content**).

**Step 4** — Update preamble using `str_replace`:

For **CVPR/ICCV**:
- Set `\documentclass[10pt,twocolumn,letterpaper]{article}`
- Add `\usepackage{cvpr}` (or `iccv`)
- Remove conflicting packages (`geometry`, `hyperref`, `multicol`)
- Comment out `\cvprfinalcopy` for submission

For **ECCV**:
- Set `\documentclass[runningheads]{llncs}`
- Remove `article`-class-specific commands
- Switch author block to LNCS syntax (`\author{}` + `\institute{}`)

**Step 5** — Anonymize for submission (remove author names/affiliations).

**Step 6** — Fix bibliography setup (see Bibliography section below).

**Step 7** — Run `latex_compile` and resolve remaining issues.

### Scenario 3: Fix Format Issues

**Step 1** — Run `latex_compile` to capture errors/warnings.

**Step 2** — Read preamble in `main.tex` and compare with downloaded sample `.tex`.

**Step 3** — Check common failures (see Common Pitfalls below):
- Missing `.sty`/`.cls`/`.bst` in project root
- `hyperref` loaded manually (CVPR/ICCV load it internally)
- `\cvprfinalcopy` left uncommented at submission
- `geometry` package conflicting with style
- Wrong document class for ECCV (`article` instead of `llncs`)

**Step 4** — Apply fixes with `str_replace`.

**Step 5** — Re-run `latex_compile` until clean.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read full `main.tex` with `read_file`.

**Step 2** — Verify checklist items:

For **CVPR/ICCV**:
- [ ] `\documentclass[10pt,twocolumn,letterpaper]{article}` is used
- [ ] `\cvprfinalcopy` is commented out for submission
- [ ] No author names/affiliations visible in submission
- [ ] `\cvprPaperID` is set correctly
- [ ] No `\usepackage{hyperref}` (style loads it)
- [ ] No `geometry` package
- [ ] Page count ≤ 8 pages content (references unlimited) — verify CFP
- [ ] Bibliography wrapped in `{\small ...}`

For **ECCV**:
- [ ] `\documentclass[runningheads]{llncs}` is used
- [ ] No author names in anonymous submission
- [ ] Total page count ≤ 14 pages INCLUDING references — verify CFP
- [ ] `\bibliographystyle{splncs04}` is used

**Step 3** — Report and fix issues one by one with `str_replace`.

**Step 4** — Run final `latex_compile` verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: The rules below reflect common patterns from recent years. Always prioritize the target year's CFP and author kit over defaults in this skill.

### Template Download

**CVPR**:
- Go to https://cvpr.thecvf.com → "Author Guidelines" or "Paper Submission"
- Download the "Author Kit" `.zip` from the official site (URL changes each year)
- Overleaf (backup): search "CVPR" on https://www.overleaf.com/latex/templates?q=CVPR

**ICCV**:
- Go to https://iccv.thecvf.com → "Author Guidelines"
- Template is nearly identical to CVPR but uses `iccv.sty` and `iccv.bst`
- Overleaf (backup): search "ICCV" on https://www.overleaf.com/latex/templates?q=ICCV

**ECCV**:
- Go to https://eccv.ecva.net → "Author Guidelines"
- ECCV uses a **Springer LNCS** template (different from CVPR/ICCV)
- Download from the ECCV site or https://www.springer.com/gp/computer-science/lncs/conference-proceedings-guidelines
- Overleaf (backup): search "ECCV" on https://www.overleaf.com/latex/templates?q=ECCV

### Setup: Unzip Location

Unzip into the **project root** (same directory as `main.tex`):

**CVPR/ICCV**:
```
project/
├── main.tex                      ← your paper
├── cvpr.sty                      ← style file (or iccv.sty for ICCV)
├── cvpr.bst                      ← bibliography style (or iccv.bst)
├── egpaper_for_review.tex        ← submission template — READ THIS
└── egpaper_final.tex             ← camera-ready template — read for final version
```

**ECCV** (Springer LNCS):
```
project/
├── main.tex
├── llncs.cls                     ← Springer LNCS class — REQUIRED at root
├── splncs04.bst                  ← bibliography style
└── samplepaper.tex               ← sample paper — READ THIS
```

### Read These Files First

**CVPR/ICCV**:
1. **`egpaper_for_review.tex`** — submission template with all preamble settings, author anonymization, figure/table examples, and bibliography setup
2. **`egpaper_final.tex`** — camera-ready template showing how to add author info and paper ID

**ECCV**:
1. **`samplepaper.tex`** — Springer sample paper with all Springer-specific macros and format rules
2. **`llncs.cls` comments** — for edge cases not covered in the sample

### CVPR / ICCV Template Setup

```latex
\documentclass[10pt,twocolumn,letterpaper]{article}

\usepackage{cvpr}          % or \usepackage{iccv} for ICCV
\usepackage{times}
\usepackage{epsfig}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}

% Include OTHER packages BEFORE hyperref:
% \usepackage{...}

% For camera-ready ONLY — uncomment AFTER acceptance:
% \cvprfinalcopy

\def\cvprPaperID{****}     % ← Replace **** with your paper ID from submission system
\def\httilde{\mbox{\tt\raisebox{-.5ex}{\symbol{126}}}}
```

**Rule**: Keep `% \cvprfinalcopy` commented out for blind review. Uncomment and set `\cvprPaperID` to your actual paper ID for camera-ready.

### ECCV Template Setup (Springer LNCS)

```latex
\documentclass[runningheads]{llncs}

\usepackage{graphicx}
\usepackage{amsmath}
\usepackage[T1]{fontenc}

% For ECCV 2024+ (check the specific year's guidelines):
\usepackage[misc]{ifsym}   % or other venue-specific packages per CFP
```

ECCV's LNCS format is fundamentally different from CVPR/ICCV — single column, numbered sections, different author macro syntax.

### Key Format Rules

#### CVPR / ICCV

| Item | Requirement |
|------|-------------|
| Page limit | Typically **8 pages** content + unlimited references — verify at https://cvpr.thecvf.com / https://iccv.thecvf.com current year CFP |
| Layout | **Two-column**, 10pt, letter paper |
| Anonymous | Blind review — no author names/affiliations in submission; paper ID shown instead |
| Camera-ready | Add `\cvprfinalcopy`, set `\cvprPaperID`, add author info |
| Supplementary | Separate PDF — verify page/size limit at current year CFP |

#### ECCV (Springer LNCS)

| Item | Requirement |
|------|-------------|
| Page limit | Typically **14 pages** total (content + references combined) — verify at https://eccv.ecva.net current year CFP |
| Layout | **Single column**, A4 paper |
| Font | Computer Modern (default LaTeX) or Times if specified |
| Anonymous | Double-blind; remove author names |

### Common Pitfalls

#### CVPR / ICCV
- **Missing `.sty` or `.bst`**: Both must be in the project root. `cvpr.sty` and `cvpr.bst` (or `iccv.sty`/`iccv.bst`) must be placed there.
- **`\cvprfinalcopy` left uncommented at submission**: If this is active, the paper is not anonymized — the header shows the paper ID but the submission is not blind. Use `egpaper_for_review.tex` as your base, which has it commented out.
- **`hyperref` loading order**: The CVPR style loads `hyperref` at the end of the preamble. Do NOT add `\usepackage{hyperref}` yourself — it causes "option clash" errors. Any packages that interact with `hyperref` (e.g., `cleveref`) must be loaded after `\usepackage{cvpr}`.
- **Two-column floats**: Use `figure*` and `table*` environments for full-width floats spanning both columns.
- **`geometry` package conflict**: Do not use `geometry` — CVPR sets margins via the document class options.

#### ECCV
- **LNCS is NOT `article` class**: Do not use `\documentclass{article}` for ECCV. Use `\documentclass[runningheads]{llncs}`.
- **Page limit includes references**: Unlike CVPR/ICCV where references are unlimited, ECCV's 14-page limit covers the entire paper including references.
- **Author block uses `\author{}` + `\institute{}`** (LNCS syntax), not standard LaTeX `\author{}` + `\affil{}`.

### Bibliography

**CVPR / ICCV**:
```latex
{\small
\bibliographystyle{ieee_fullname}   % or cvpr.bst / iccv.bst
\bibliography{references}
}
```
Wrap the bibliography in `{\small ...}` to match the template. Some years use `ieee_fullname.bst`; check `egpaper_for_review.tex` for the exact `.bst` name used.

**ECCV (LNCS)**:
```latex
\bibliographystyle{splncs04}    % Springer's official .bst
\bibliography{references}
```
