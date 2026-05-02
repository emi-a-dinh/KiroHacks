# Project Memory

## 2026-05-02 — Hook setup and review

**What changed:**
- `.kiro/hooks/auto-reindex-on-save.kiro.hook` — removed broken shell redirect (`>> ... 2>&1`) so the command runs cleanly through the hook runner
- `.kiro/hooks/test-after-task.kiro.hook` — added `--tb=short` for more actionable failure output
- `.kiro/hooks/commit-helper.kiro.hook` — new user-triggered hook that reviews staged diffs and suggests conventional commit messages
- `.kiro/hooks/memory-consolidator.kiro.hook` — new agentStop hook that appends session summaries to this file

**Decisions made:** Kept reindex hook running against workspace root (`.`) since both `context-lens/` and `example_project/` live here. Commit helper is manual trigger rather than automatic to avoid noise.

**Issues encountered:** The original reindex hook used shell redirects (`>>`, `2>&1`) in `runCommand`, which the hook runner doesn't reliably interpret — command was silently failing. Fixed by removing the redirect since `--quiet` already suppresses normal output.

**Open items:** None from this session.

## 2026-05-02 — Auto-commit hook and session commit

**What changed:**
- `.kiro/hooks/commit-helper.kiro.hook` — changed from `userTriggered` to `agentStop` so it auto-commits after every agent interaction
- Auto-committed staged changes: new hooks, memory file, updated query modules, token-miser scaffold

**Decisions made:** Commit hook stages everything (`git add -A`) and commits automatically. Conventional commit format enforced via the hook prompt.

**Issues encountered:** None.

**Open items:** The auto-commit hook and memory-consolidator both fire on `agentStop` — watch for ordering issues if both try to write and commit in the same cycle.
