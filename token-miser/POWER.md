---
name: "token-miser"
displayName: "Token Miser"
description: "Index a codebase and select only the relevant files, symbols, and call graph context for coding tasks"
keywords: ["token miser", "miser", "miser_fix", "miser_ask", "miser_plan", "context", "codebase", "index", "tokens", "signatures", "call graph", "mcp"]
author: "KiroHacks"
---

# Token Miser

You are working inside a code repository.
Before reading large amounts of code or selecting files manually, you must use Token Miser.

## Available MCP Server

### token-miser

The `token-miser` MCP server provides repository indexing and focused context selection tools.

## Available commands

- `miser_fix` — For bug fixes or implementation tasks
- `miser_ask` — For questions about the codebase
- `miser_plan` — For multi-step or unclear tasks

## How to prompt

Use command-style prompts when you want Token Miser to run first:

```text
miser_fix Add auth middleware and user attribution before writes
miser_ask How does idea creation work?
miser_plan Add moderation states to ideas
```

When a prompt starts with `miser_fix`, `miser_ask`, or `miser_plan`, call the matching MCP tool before using workspace search or file reads.

## Rules

Always prefer miser commands over manual file reading.

- For questions about the codebase → Use `miser_ask`
- For bug fixes or implementation → Use `miser_fix`
- For multi-step or unclear tasks → Use `miser_plan`

## Do not

- Open entire files unless necessary
- Paste large amounts of code into context
- Manually search the repo first

## Token Miser will

- Index the repo automatically
- Select relevant units (functions, classes, methods)
- Expand only needed code
- Include call graph neighbors and related tests

## After running miser_fix

1. Apply the changes to the repo
2. Run tests if available
3. Summarize changes

## If Token Miser output is insufficient

- Expand additional related units
- Do not fall back to full file reads immediately

## Keywords

fix, ask, plan, context, index, codebase, tokens, signatures, functions, classes, call graph, miser
