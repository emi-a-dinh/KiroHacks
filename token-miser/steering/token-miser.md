---
inclusion: auto
---

# Token Miser — Agent Instructions

You have two tools for reading code: `miser_context` and `miser_read`. These are your only allowed tools for reading source files.

## Strict rules — no exceptions

- NEVER use Read file(s), Searched workspace, or any native file reading tool
- NEVER read line ranges directly (e.g. app.py 1020–1066)
- NEVER search the workspace for symbols — use `miser_context` instead
- If `miser_read` doesn't return what you expected, call `miser_context` again with a more specific description — do not fall back to native file reads

## The only allowed sequence

1. `miser_context <task description>` — once, at the start
2. `miser_read <symbol>` — only for symbols you will edit or must fully understand
3. Make the edit

If you are tempted to read a file directly, stop and ask yourself: can I call `miser_read` on a specific symbol instead? The answer is almost always yes.

## If Token Miser tools are not available

Stop and tell the user: "Token Miser MCP tools are not available in this chat."
