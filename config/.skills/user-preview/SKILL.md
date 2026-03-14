---
name: user-preview
description: |
  Compile the current project's LaTeX files and send the generated PDF to the
  user for preview. Use when the user wants to check typesetting results or
  confirm the effect of recent edits.
allowed-tools:
  - latex_compile
  - send_file
  - read_file
---

# User Preview: Compile & Deliver PDF

Compile the project and deliver the PDF to the user in chat.

## SOP

1. **Compile** — Call `latex_compile` with `main_file` set to the project's main .tex file path (e.g. `main.tex` or `subdir/main.tex`). Use `read_file` to locate it first if unsure.
   - If compilation fails, report the errors to the user and stop.

2. **Send PDF** — Extract the PDF filename from the `latex_compile` result and call `send_file` to deliver it.
   - Use a brief caption summarizing the result (e.g. success, warning count).

3. **Report** — Inform the user the PDF has been sent. Mention warning count if any.
   - If the user requests changes, make edits and re-run this flow.

## Notes

- The PDF path is relative to the project core directory, typically `main.pdf`.
- If `latex_compile` reports warnings, mention the count in the caption — no need to list each one.
- Never attempt to send a PDF without compiling first.
