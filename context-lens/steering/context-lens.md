---
inclusion: auto
---

# Context Lens — Agent Instructions

You have access to Context Lens, which automatically indexes the codebase and selects relevant code for any task.

## When the user describes a task

1. **Bug fix or implementation** → Call `lens_fix` with the task description.
   The tool will auto-index, select relevant code (including tests and call graph neighbors), and return structured context with fix instructions.

2. **Question about the codebase** → Call `lens_ask` with the question.
   Returns relevant code with explanation instructions. No edits.

3. **Multi-step or unclear task** → Call `lens_plan` with the task description.
   Returns relevant code with a planning prompt. No edits until the user confirms.

## After receiving lens_fix output

1. Read the selected code and instructions.
2. Implement the fix in the relevant files.
3. Run tests if a test runner is available.
4. Summarize what changed.

## Rules

- **Do not read entire files** unless the lens output is clearly insufficient.
- **Do not manually search** the repo before calling lens.
- **Prefer minimal context** — only use the code returned by Context Lens.
- If the selection confidence is "low", expand additional related units before proceeding.
- If the user provides an error log, pass it via the `error_log` parameter.
