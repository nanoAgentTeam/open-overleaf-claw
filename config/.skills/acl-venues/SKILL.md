---
name: acl-venues
description: "ACL-family venue paper formatting (ACL, EMNLP, NAACL, EACL, AACL, COLING, ARR, Findings) — activate when the user wants any ACL-series template setup, migration, or format fixes."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
  - latex_compile
---
[SKILL: ACL-FAMILY VENUE PAPER FORMAT]

Activate when: user mentions ACL, EMNLP, NAACL, EACL, AACL, COLING, ARR, Findings of ACL, or asks to use/fix any *ACL-series template.

## Execution Protocol

After this skill is activated, select the matching scenario based on user intent.

### Shared Common Workflow

Before venue-specific template steps, also load and follow `ml-paper-writing` skill.

At minimum, apply these shared references:
- `writing-guide.md` (narrative and clarity)
- `citation-workflow.md` (verified citations; no hallucinations)
- `reviewer-guidelines.md` (reviewer-facing quality checks)
- `checklists.md` (pre-submission gates)

**Built-in template**: `templates/acl/` (referred to as `TEMPLATES_DIR` below).
Contents: `acl.sty`, `acl_latex.tex`, `acl_natbib.bst`, `custom.bib`, `anthology.bib.txt`, `formatting.md`.

**One template for all ACL-family venues**: ACL, EMNLP, NAACL, EACL, AACL, COLING, ARR, and Findings generally share the same `acl.sty` + `acl_natbib.bst` style system; venue differences are mainly page limits and policy text.

### Pre-step: Venue/Year/Track Confirmation & Template Source

**This step MUST be completed before any scenario below.**

1. Confirm target venue and year (ACL/EMNLP/NAACL/EACL/AACL/COLING/ARR/Findings), plus paper type (long/short) and stage (review/final). Default to latest available year if user does not specify.
2. Check whether local `TEMPLATES_DIR` exists and includes required files: `acl.sty`, `acl_natbib.bst`, `acl_latex.tex`.
3. **Use local built-in template only when BOTH conditions hold**:
   - local files in `TEMPLATES_DIR` are complete
   - target venue/year does not require a different package than `acl.sty`
4. **If either condition fails** (local files missing/incomplete OR user asks for strict current-year kit), follow this download workflow exactly:
   - Go to official ACLPUB portal: https://acl-org.github.io/ACLPUB/
   - Open the target venue's CFP/submission page and find "Style Files", "Author Kit", or "Submission Instructions"
   - Download the official style zip for the target year
   - If the venue page is unclear, use fallback sources:
     - GitHub zip: https://github.com/acl-org/acl-style-files/archive/refs/heads/master.zip
     - Overleaf template: https://www.overleaf.com/latex/templates/association-for-computational-linguistics-acl-conference/jvxskxpnznfj
   - Unzip downloaded files directly into <PROJECT_CORE>.
   - Verify required files exist (`acl.sty`, `acl_natbib.bst`, sample `.tex`)
   - Continue all remaining steps using filenames from the downloaded kit if they differ
5. **Filename substitution rule for all steps below**:
   - Treat `acl` / `acl_natbib` in commands/examples as defaults.
   - If the downloaded kit uses different basenames, replace them consistently in `\\usepackage`, `\\bibliographystyle`, copy commands, and checks.

### Scenario Routing

- User says "create / new ACL-family paper" → **Scenario 1**
- User says "switch to ACL format" / "apply ACL template" → **Scenario 2**
- User says "ACL format issue" / "compile error" → **Scenario 3**
- User says "check format" / "prepare for submission" → **Scenario 4**

Treat all ACL-family venue requests with the same 4 scenarios above unless the target CFP requires a different style package.

### Scenario 1: Create a New ACL-Family Project

**Step 1** — Copy style files to the project core directory using `bash`:
```
bash(command="cp TEMPLATES_DIR/acl.sty TEMPLATES_DIR/acl_natbib.bst <PROJECT_CORE>/")
```

**Step 2** — Read `TEMPLATES_DIR/acl_latex.tex` with `read_file` for canonical preamble, title/author layout, and bibliography usage.

**Step 3** — Create `main.tex` in the project core directory using `write_file`:
- `\documentclass[11pt]{article}`
- For anonymous review: `\usepackage[review]{acl}`
- For camera-ready/final: `\usepackage{acl}`
- Keep core packages aligned with template (`times`, `latexsym`, `fontenc`, `inputenc`; optional `microtype`)
- Set title/author block according to review vs final stage
- Use `\bibliographystyle{acl_natbib}` and `\bibliography{custom}` (or project bib filename)

**Step 4** — Run `latex_compile` to verify successful compilation. If it fails, read the log and fix errors.

### Scenario 2: Switch an Existing Project to ACL Template

**Step 1** — Read current `main.tex` with `read_file` to analyze existing preamble and structure.

**Step 2** — Read `TEMPLATES_DIR/acl_latex.tex` with `read_file` as the migration reference.

**Step 3** — Copy style files using `bash` (**style files only — do NOT overwrite user content**):
```
bash(command="cp TEMPLATES_DIR/acl.sty TEMPLATES_DIR/acl_natbib.bst <PROJECT_CORE>/")
```

**Step 4** — Modify `main.tex` preamble using `str_replace`:
- Set `\documentclass[11pt]{article}`
- Set `\usepackage[review]{acl}` for submission or `\usepackage{acl}` for final
- Keep encoding/font packages required by template
- Remove layout-breaking/conflicting packages (`geometry`, manual margin hacks, `multicol`, custom page size overrides)

**Step 5** — Fix ACL-specific structure:
- Review mode: no identifying text, no acknowledgements
- Final mode: restore author and affiliation block
- If title/author block overflows, set `\setlength\titlebox{<dim>}` with `<dim> >= 5cm`

**Step 6** — Fix bibliography:
- `\bibliographystyle{acl_natbib}`
- `\bibliography{custom}` (or existing project bib file)

**Step 7** — Run `latex_compile` and resolve any remaining errors.

### Scenario 3: Fix ACL Format Issues

**Step 1** — Run `latex_compile` to capture current errors/warnings.

**Step 2** — Read `main.tex` preamble and compare with `TEMPLATES_DIR/acl_latex.tex`.

**Step 3** — Cross-check against common ACL failures:
- Missing `acl.sty` or `acl_natbib.bst` in project root
- Wrong mode (`\usepackage{acl}` vs `\usepackage[review]{acl}`)
- `\bibliographystyle` not set to `acl_natbib`
- Manual layout overrides (`geometry`, `\onecolumn`, custom margins)
- Review draft still contains acknowledgements or identifying information

**Step 4** — Apply fixes using `str_replace`.

**Step 5** — Re-run `latex_compile` until clean.

### Scenario 4: Pre-submission Format Compliance Check

**Step 1** — Read full `main.tex` with `read_file`.

**Step 2** — Verify checklist items:
- [ ] Correct review/final mode (`[review]` for submission)
- [ ] Anonymization for review (no author identity, no acknowledgements)
- [ ] Page limits match CFP (typical review limits: long 8 pages / short 4 pages, references excluded)
- [ ] A4 two-column layout intact (no forbidden margin/layout overrides)
- [ ] Bibliography style is `acl_natbib`
- [ ] Review version includes ruler/line numbers; final version removes them
- [ ] References and appendices follow venue rules for the target year

**Step 3** — Report violations and fix them one by one with `str_replace`.

**Step 4** — Run final `latex_compile` verification.

---

## Format Reference

> ⚠️ **Reference only — always verify**: ACL-family requirements can change by venue/year. Always treat the target year's CFP and official author kit as source of truth.

### Template Download

- Official ACLPUB portal: https://acl-org.github.io/ACLPUB/
- Official style repo zip: https://github.com/acl-org/acl-style-files/archive/refs/heads/master.zip
- Overleaf template: https://www.overleaf.com/latex/templates/association-for-computational-linguistics-acl-conference/jvxskxpnznfj

### Setup: Unzip Location

Unzip into project root (same folder as `main.tex`):
```
project/
├── main.tex
├── acl.sty
├── acl_natbib.bst
├── acl_latex.tex
└── custom.bib
```

### Read These Files First

1. `acl_latex.tex` — canonical sample for preamble and structure
2. `formatting.md` — ACL formatting requirements and page-limit policy
3. `acl.sty` comments — option behavior (`review`, `preprint`, final)

### Template Setup in `main.tex`

```latex
\documentclass[11pt]{article}

% Submission (anonymous + line numbers)
\usepackage[review]{acl}

% Camera-ready:
% \usepackage{acl}

\usepackage{times}
\usepackage{latexsym}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{microtype}
```

### Key Format Rules

| Item | Requirement |
|------|-------------|
| Layout | A4, two-column (except title/author region and full-width figures/tables) |
| Review anonymity | No identifying author info; no acknowledgements |
| Bibliography | `acl_natbib` style |
| Page limits | Follow target CFP (common review defaults: long 8, short 4 pages of content) |
| Final version | Remove review-only ruler/line numbers |

### Common Pitfalls

- Using `geometry` or manual margin hacks that break ACL layout
- Wrong package mode (`acl` instead of `[review]` during submission)
- Forgetting `acl_natbib` bibliography style
- Keeping acknowledgements in review submission
- Ignoring venue-specific limits for workshops/Findings tracks
