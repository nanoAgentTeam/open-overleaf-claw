# Configuration and Quick Start

## Quick Start

```bash
# 1. Environment setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Launch Gateway (includes Web UI)
python cli/main.py gateway --port 18790

# 3. Open the Web UI in your browser to configure
#    http://localhost:18790/ui
#    - Go to "Provider Management" to add an LLM provider (API Key, model name, etc.)
#    - Go to "Channel Accounts" to configure IM bots (optional)
#    - Go to "Push Subscriptions" to set up notification channels (optional)

# 4. Configure Overleaf sync (optional)
pip install overleaf-sync
ols login  # generates .olauth cookie file

# 5. Or use CLI mode for interactive sessions
python cli/main.py agent
```

> **Tip**: All configuration can be done through the Web UI. Settings are stored in `settings.json` — advanced users can also edit this file directly.

## Configuration Files

| File | Purpose |
| --- | --- |
| `settings.json` | Unified runtime config (LLM providers, IM accounts, push subscriptions, gateway, etc.) — managed via Web UI |
| `config/tools.json` | Tool registry (enable/disable, mode authorization, role restrictions) |
| `config/agents.json` | SubAgent global configuration (merge_to_core, etc.) |
| `config/commands.json` | Slash command definitions |
| `workspace/{project}/project.yaml` | Project-level configuration (Git, Overleaf, LaTeX engine) |

## System Diagnostics

To verify your configuration is correct:

```bash
python cli/main.py doctor
```
