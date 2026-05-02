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

## 2026-05-02 — Token Miser: full rename and v2 selector

**What changed:**
- `token-miser/` — complete copy of `context-lens/` renamed: CLI (`miser`), MCP tools (`miser_fix/ask/plan`), index dir (`.token-miser/`), hooks, steering, POWER.md, pyproject.toml
- `token-miser/src/query/selector.py` — rewrote with 6 improvements: fixed camelCase tokenizer, domain alias expansion (20+ alias groups), stricter sibling selection (score > 0 or shared name tokens), smarter test discovery (file name + function name + code references + route strings), coverage-based confidence (5 weighted signals), explainable selection (reasons per unit + coverage dict)
- `token-miser/src/query/smart.py` — updated to use new `SelectionResult` dataclass, outputs `## Selection Coverage` block and per-unit `# Selected because:` comments
- `~/.kiro/settings/mcp.json` — updated to point at token-miser MCP server with new tool names

**Decisions made:** Kept `context-lens/` folder intact as reference. Token Miser is the user-facing name going forward. Confidence uses coverage-based scoring (target_found, similar_pattern, dependency, test, error_file) instead of raw top-score thresholds.

**Issues encountered:** Initial `cp -r context-lens token-miser` nested the folder incorrectly — had to redo with `cp -r context-lens/ token-miser/`. Python 3.9 compatibility required replacing `str | None` union syntax with `Optional[str]`.

**Open items:** `context-lens/` folder can be deleted once token-miser is confirmed stable. Should add `.gitignore` for `__pycache__/`, `.token-miser/`, `.context-lens/` dirs.
