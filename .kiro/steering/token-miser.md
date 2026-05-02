---
inclusion: auto
---

# Token Miser — Agent Instructions

You have access to Token Miser, which automatically indexes the codebase and selects relevant code for any task.

## When the user describes a task

1. **Bug fix or implementation** → Call `miser_fix` with the task description.
2. **Question about the codebase** → Call `miser_ask` with the question.
3. **Multi-step or unclear task** → Call `miser_plan` with the task description.

## After receiving miser_fix output

1. Read the selected code and instructions.
2. Implement the fix in the relevant files.
3. Run tests if a test runner is available.
4. Summarize what changed.

## Rules

- Do not read entire files unless the miser output is clearly insufficient.
- Do not manually search the repo before calling miser.
- Prefer minimal context — only use the code returned by Token Miser.
- If the selection confidence is "low", expand additional related units before proceeding.
- If the user provides an error log, pass it via the `error_log` parameter.
