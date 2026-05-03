---
inclusion: auto
---

# Token Miser — Agent Instructions

You have access to Token Miser, which automatically indexes the codebase and selects relevant code for any task.

## Command-style prompts

If the user's message starts with one of these command names, treat it as an explicit tool-use instruction:

- `miser_fix <task>` → immediately call the MCP tool `miser_fix` with `task` set to `<task>`
- `miser_ask <question>` → immediately call the MCP tool `miser_ask` with `question` set to `<question>`
- `miser_plan <task>` → immediately call the MCP tool `miser_plan` with `task` set to `<task>`

For command-style prompts, do not search the workspace, read files, inspect folders, or explain your plan before the Token Miser tool call. The first action must be the corresponding MCP tool call.

If the requested Token Miser MCP tool is not available in the tool list, stop and tell the user: "Token Miser MCP tools are not available in this chat." Do not silently fall back to workspace search.

## When the user describes a task

1. **Bug fix or implementation** → Call `miser_fix` with the task description.
2. **Question about the codebase** → Call `miser_ask` with the question.
3. **Multi-step or unclear task** → Call `miser_plan` with the task description.

## After receiving miser_fix output

1. Read the selected code and instructions.
2. Implement the fix in the relevant files.
3. Run tests if a test runner is available.
4. Summarize what changed.

Do not override Token Miser by searching or reading files after a `miser_fix` result. If the result is high or medium confidence, treat the selected code as the complete allowed context. If the context is insufficient, stop and tell the user what Token Miser missed instead of opening more files.

## Rules

- Do not read entire files unless the miser output is clearly insufficient.
- Do not manually search the repo before calling miser.
- Prefer minimal context — only use the code returned by Token Miser.
- If Token Miser returns enough context to make the change, do not open the same files manually.
- Never use workspace search/read/list as a silent fallback after a successful `miser_fix` tool call.
- If the selection confidence is "low", expand additional related units before proceeding.
- If the user provides an error log, pass it via the `error_log` parameter.
