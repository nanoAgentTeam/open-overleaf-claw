# Workspace and Session

## Two Spaces: Default and Project

The system has two workspaces, each serving different purposes:

| | Default (Lobby) | Project (Workspace) |
|---|---------|---------|
| Purpose | Chat, browse project list, create/link projects | Work within a specific project |
| Available Tools | Project management, Overleaf list/create, general tools | File read/write, LaTeX compilation, Bash, SubAgent, etc. |
| File Operations | Does not directly manipulate project files | Directly reads/writes files in the core directory |

After startup, you are in Default by default. Tell the Bot "switch to project xxx" to enter the corresponding Project workspace.

## Workspace Directory Structure

```
workspace/
├── Default/                    # Default workspace (chat, project management)
│   └── cli:default/            # CLI default session
├── MyPaper/                    # A paper project
│   ├── project.yaml            # Project configuration (git, overleaf, latex)
│   ├── MyPaper/                # core directory (actual paper files)
│   │   ├── .git/
│   │   ├── main.tex
│   │   ├── references.bib
│   │   └── ...
│   ├── 0217_01/                # session (MMDD_NN format)
│   │   ├── .bot/               # session metadata, conversation history
│   │   ├── artifacts/
│   │   └── subagents/          # SubAgent working directory (overlay)
│   └── 0217_02/                # another session
└── AnotherPaper/
```

Key concepts:

- **core directory**: `workspace/{project_name}/{project_name}/`, stores the actual paper files (.tex, .bib, etc.) and is an independent Git repository. When the Agent enters a project, the working directory is this core.
- **session directory**: `workspace/{project_name}/{MMDD_NN}/`, created each time you enter a project, isolating conversation history and SubAgent workspaces.

## Session

Each time you switch into a project, a new session is created (format `MMDD_NN`, e.g., `0217_01`). A Session isolates:

- Conversation history (each session has independent history)
- SubAgent working directories
- Metadata and trace logs

You can also pass an existing session name to resume previous work — you don't have to create a new one every time.

## Ways to Enter a Workspace

1. After starting the CLI, you are in Default
2. Use natural language to say "switch to project xxx", or "create a new project"
3. The Bot executes the project_manager tool to complete the switch
4. After switching, the prompt changes to show the current project and session name
5. Use `/back` to return to Default
