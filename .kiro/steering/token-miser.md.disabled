---
inclusion: auto
---

# Token Miser — Agent Instructions

You have access to two tools: `miser_context` and `miser_read`.

When given a coding task, always follow this exact sequence without waiting for input:

1. Call `miser_context` with the task description immediately.
2. Read the signatures it returns.
3. Call `miser_read` on every symbol you need to fully understand or edit to complete the task — do this in parallel if possible.
4. Then complete the task.

Never ask the user which functions to read. Never skip `miser_context`. Never read a function you don't need. If `miser_context` returns nothing useful, tell the user what's missing rather than guessing.

## If Token Miser tools are not available

Stop and tell the user: "Token Miser MCP tools are not available in this chat."
