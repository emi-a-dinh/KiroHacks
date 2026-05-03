---
inclusion: auto
---

# Token Miser — Agent Instructions

You have access to two tools: `miser_context` and `miser_read`.

When given a coding task, always follow this exact sequence without asking for confirmation:

1. Call `miser_context` with the task description.
2. Read the returned signatures.
3. Call `miser_read` on each symbol you need to edit or fully understand.
4. Before editing any file, call `miser_read` again on the exact symbol you're about to change — never trust a previously read version, always re-read immediately before writing.
5. Make the edit.

Never edit based on a stale `miser_read` result. If the source you read doesn't match what you expected from the signatures, re-index by calling `miser_context` again before proceeding. Never guess at function contents.

## If Token Miser tools are not available

Stop and tell the user: "Token Miser MCP tools are not available in this chat."
