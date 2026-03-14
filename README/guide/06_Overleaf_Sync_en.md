# Overleaf Sync

## Linking an Overleaf Project

In Default, you can:

- Create a new project and simultaneously create one on Overleaf, automatically linking them
- Link an existing Overleaf project: first list the Overleaf project list, get the ID, then link

In practice, just tell the Bot in natural language, e.g., "create a paper project and link it to Overleaf", and the Bot will automatically complete all steps.

## Pull & Push (Not Yet Fully Verified)

| Operation | Trigger Method | Description |
|------|----------|------|
| Pull | Automatically triggered on switch / `/sync pull` | Downloads the latest files from Overleaf; locally modified files are not overwritten |
| Push | `/sync push` | Pushes local changes to Overleaf (additions, modifications, deletions) |

Pull/Push behavior is configured in `project.yaml`, including the Overleaf project ID and whether to auto-pull.

## Authentication

Requires a `.olauth` file (Overleaf login Cookie). Generated via the `ols login` command, placed in `.bot_data/.olauth` or the project root directory.
