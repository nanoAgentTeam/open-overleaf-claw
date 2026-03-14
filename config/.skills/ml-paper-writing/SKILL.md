---
name: ml-paper-writing
description: "Use when writing or revising any ML/AI paper (conference or journal) to apply shared writing quality, citation verification, reviewer-aligned checks, and pre-submission gates."
allowed-tools:
  - read_file
  - write_file
  - str_replace
  - bash
---
[SKILL: ML PAPER COMMON WORKFLOW]

Activate when: user asks to write/revise/check any ML/AI paper, regardless of venue (conference or journal).

## Purpose

This skill is the shared, venue-agnostic layer. Venue-specific skills should handle template/macros/page limits, while this skill handles writing quality, citation integrity, reviewer alignment, and submission checks.

## Coverage Boundary

- This skill covers **common writing/citation/review SOP** for both conferences and journals.
- This skill does **not** provide journal-specific template setup (`.cls/.sty/.bst`, submission system steps, journal-only formatting policies).
- For journals, pair this skill with the journal's official author guide or a journal-specific venue skill.

## Required Reference Files

Use these references from `references/` as the source of truth:

1. `writing-guide.md` — paper narrative and section-level writing quality
2. `citation-workflow.md` — verified citation workflow and hallucination prevention
3. `reviewer-guidelines.md` — reviewer evaluation lenses and rebuttal-oriented checks
4. `checklists.md` — mandatory checklist gates before submission

## Execution Workflow

### Step 1: Clarify Scope

- Confirm paper type: conference or journal
- Confirm current stage: first draft / revision / camera-ready
- Confirm what is venue-specific vs common writing work

### Step 2: Apply Writing Quality Workflow

- Use `writing-guide.md` to enforce:
  - clear contribution framing
  - precise claims and evidence alignment
  - section-level coherence (abstract, intro, method, results, limitations)

### Step 3: Apply Citation Integrity Workflow

- Follow `citation-workflow.md` strictly
- Never fabricate citations from memory
- If citation cannot be verified, mark as explicit placeholder and report it

### Step 4: Apply Reviewer Lens

- Use `reviewer-guidelines.md` to evaluate:
  - technical soundness
  - novelty/significance
  - clarity and reproducibility
- Add missing evidence/ablation/limitations where needed

### Step 5: Run Submission Gates

- Use `checklists.md` and complete all applicable items
- If any required item is missing, block "ready to submit" status and list the gaps

## Handoff Rule to Venue Skills

- Venue skills own:
  - template selection and setup (`.cls/.sty/.bst`)
  - anonymization mode and page limits
  - venue-specific required sections and package restrictions
- This skill owns common writing/citation/review/checklist quality gates.

Use both layers together: `ml-paper-writing` + target venue skill.
