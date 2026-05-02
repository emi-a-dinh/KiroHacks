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
