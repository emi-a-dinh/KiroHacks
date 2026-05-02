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

## How it works

1. Indexes your codebase into a local SQLite database
2. Extracts function/class signatures and call edges
3. Auto-selects relevant code for any task description
4. Returns only the code you need — 10-15x fewer tokens
