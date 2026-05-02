# Context Lens

Index your codebase once. Query it fast. Context Lens builds a signature-level
map of your repo — every function, class, and method with their call relationships
— so your agent can find the relevant code without reading every file.

## What it does

- Indexes source files into a local SQLite database (Python, JS/TS supported)
- Extracts function/class signatures and lightweight call edges
- Handles incremental updates — only re-parses changed files
- Detects moved/renamed files and preserves their index entries
- Returns compact signature maps and expanded code blocks on demand

## Tools

- `context_index` — index or re-index a repository
- `context_query` — get the signature map for a task
- `context_expand` — expand selected unit IDs into full source code

## Keywords

index, codebase, context, tokens, signatures, functions, classes, call graph

## Requirements

This Power requires `uv` to be installed. If you don't have it:
- macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Or see: https://docs.astral.sh/uv/getting-started/installation/
