# Token Miser

You are working inside a code repository.
Before reading large amounts of code or selecting files manually, you must use Token Miser.

## Available commands

- `lens_fix` — For bug fixes or implementation tasks
- `lens_ask` — For questions about the codebase
- `lens_plan` — For multi-step or unclear tasks

## Rules

Always prefer lens commands over manual file reading.

- For questions about the codebase → Use `lens_ask`
- For bug fixes or implementation → Use `lens_fix`
- For multi-step or unclear tasks → Use `lens_plan`

## Do not

- Open entire files unless necessary
- Paste large amounts of code into context
- Manually search the repo first

## Token Miser will

- Index the repo automatically
- Select relevant units (functions, classes, methods)
- Expand only needed code
- Include call graph neighbors and related tests

## After running lens_fix

1. Apply the changes to the repo
2. Run tests if available
3. Summarize changes

## If Token Miser output is insufficient

- Expand additional related units
- Do not fall back to full file reads immediately

## Keywords

fix, ask, plan, context, index, codebase, tokens, signatures, functions, classes, call graph
