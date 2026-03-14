# Git Version Control

Each project's core directory is an independent Git repository.

## Auto Commit

When `git.auto_commit: true` is configured in `project.yaml`, all written files are automatically committed after each turn. Commit message format: `[bot] Edit main.tex, references.bib`.

This means you can roll back to any previous modification at any time, without worrying about losing the Bot's changes.

## Git Agent (/git)

Type `/git` to enter the interactive Git management sub-session, where you can manage versions using natural language:

```
[moe:0217_01] You: /git
🔧 [Git Mode] Entering version management.

[Git] You: What changes were made recently
[Git] 🤖 (displays commit history)

[Git] You: Go back to the sync commit
[Git] 🤖 (shows the scope of impact, waits for confirmation before executing rollback)

[Git] You: /done
🔧 Exiting Git mode. [Rolled back 2 commits]
```

Available operations: view history, view status, view diff, revert commits, restore files, discard uncommitted changes.

Destructive operations (revert, discard) must first display the scope of impact and wait for user confirmation before executing.
