# Context Lens

Signature-level code indexing for LLM context optimization.

## What it does

Context Lens indexes your codebase into a compact signature map — every function, class, and method with their call relationships. Instead of sending 150k+ tokens of full file contents to an LLM, you send an 8k token signature map, let the LLM pick the relevant functions, then expand only those. Result: 10-15x fewer tokens, faster responses, lower cost.

## Quick Start

### CLI Usage

```bash
# Index a repository
python src/cli.py index /path/to/repo

# Generate a signature map for a task
python src/cli.py query "Fix the pagination bug in the /users endpoint"

# Expand specific units (use IDs from the signature map)
python src/cli.py expand "12,45,46" --task "Fix the pagination bug"

# Expand with 1-hop neighbors (callers and callees)
python src/cli.py expand "12" --neighbors --task "Trace the bug"
```

### As a Kiro Power

1. Install the Context Lens power from the Kiro Powers panel
2. The steering file will automatically index your workspace
3. Just describe your task — Kiro will use the signature map to find relevant code

### As an MCP Server

Add to your MCP config:

```json
{
  "mcpServers": {
    "context-lens": {
      "command": "python",
      "args": ["/path/to/context-lens/src/mcp_server.py"]
    }
  }
}
```

## Features

- **Signature extraction**: Functions, classes, methods, constants
- **Call edge detection**: Tracks which functions call which
- **Incremental indexing**: Only re-parses changed files
- **Move detection**: Renames/moves preserve unit IDs and edges
- **Multi-language**: Python (AST), JavaScript/TypeScript (tree-sitter or regex fallback)
- **Neighbor expansion**: Include callers/callees with one flag

## How it works

1. **Index**: Parse source files, extract signatures, store in SQLite
2. **Query**: Generate a compact signature map with call edges
3. **Expand**: Retrieve full source code for selected units

The signature map is small enough to fit in context. The LLM reads it, picks the relevant functions, and you expand only those. No more sending entire files.

## Project Structure

```
context-lens/
├── POWER.md              # Kiro Power description
├── mcp.json              # MCP server config
├── steering/             # Kiro steering files
├── src/
│   ├── cli.py            # Command-line interface
│   ├── mcp_server.py     # MCP server
│   ├── indexer/          # Parsing and indexing
│   ├── storage/          # SQLite database
│   └── query/            # Signature map and expansion
```

## Requirements

- Python 3.10+
- Optional: `tree-sitter-languages` for better JS/TS parsing

```bash
pip install tree-sitter-languages
```

## License

MIT
