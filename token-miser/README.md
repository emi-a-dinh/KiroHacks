# Token Miser

Smart context selection for coding agents. Index once, query fast.

## Usage

```bash
miser fix "fix the auth bypass on GET task"
miser ask "how does the login flow work?"
miser plan "add sorting to the task list"
miser tree
miser index
```

No manual indexing, unit IDs, or expansion needed. Just describe the task.

## Install

```bash
pip install -e token-miser/
```

## Codex MCP setup

Codex reads MCP server definitions from `~/.codex/config.toml`. Add this block:

```toml
[mcp_servers.token_miser]
command = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
args = ["/Users/edinhdawg/Documents/KiroHacks/token-miser/src/mcp_server.py"]
startup_timeout_sec = 20.0
```

The server exposes these tools:

- `miser_fix`
- `miser_ask`
- `miser_plan`
- `miser_context`
- `miser_read`

After updating the config, restart Codex so it reloads MCP servers.

## How it works

1. Indexes your codebase into a local SQLite database
2. Extracts function/class signatures and call edges
3. Auto-selects relevant code for any task description
4. Returns only the code you need — 10-15x fewer tokens
