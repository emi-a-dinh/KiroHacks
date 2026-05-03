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

## 2026-05-02 — Activate Token Miser power in workspace

**What changed:**
- `.kiro/steering/token-miser.md` — copied from `token-miser/steering/` so Kiro auto-includes it
- `.kiro/hooks/miser-reindex-on-save.kiro.hook` — copied from `token-miser/hooks/` to activate file-save re-indexing
- `.kiro/hooks/miser-reindex-on-delete.kiro.hook` — copied from `token-miser/hooks/` to activate file-delete re-indexing

**Decisions made:** Local Kiro Powers aren't auto-installed from a subfolder — steering and hooks must live in `.kiro/` to be active. MCP config was already in `~/.kiro/settings/mcp.json` from earlier.

**Issues encountered:** None.

**Open items:** If Token Miser is published as a proper Kiro Power in the registry, the manual copy step goes away. For now this is the correct local setup.

## 2026-05-02 — Full build session: PRD → Context Lens → Token Miser

**What changed:**
- `start.md` — wrote full PRD iteratively: signature-level indexing, call edges, move detection, MCP server, Kiro Power distribution
- `context-lens/` — built complete implementation: indexer (Python AST + tree-sitter + regex fallback), SQLite storage, edge builder, signature map formatter, expander, tree view, CLI (`lens`), MCP server
- `example_project/` — Flask task management API with 10 deliberate issues (auth bypass, missing pagination, MD5 passwords, N+1 queries, incomplete tests)
- `token-miser/` — renamed from context-lens: CLI (`miser fix/ask/plan/tree/index`), MCP tools (`miser_fix/ask/plan`), v2 selector with 6 improvements
- `token-miser/src/query/selector.py` — v2: camelCase tokenizer fix, domain alias expansion, stricter siblings, smarter test discovery, coverage-based confidence, explainable selection with reasons
- `token-miser/src/query/smart.py` — combines index + select + expand into single `run_fix/ask/plan` calls, outputs coverage block
- `.kiro/steering/token-miser.md`, `.kiro/hooks/miser-reindex-*` — activated in workspace

**Decisions made:** Two-phase architecture (signature map → expand) offloads relevance judgment to the LLM. Hooks keep index fresh on save/delete so smart commands skip re-indexing. `context-lens/` kept as reference. Token Miser is the user-facing name.

**Issues encountered:** Python 3.9 compatibility (union types), `cp -r` nesting, relative imports across package boundaries (solved with lazy imports and `sys.path` manipulation).

**Open items:** Kiro Powers can be installed from local folders — the manual `.kiro/` copy may be redundant if installed via the Powers panel. Should add `.gitignore` for `__pycache__/` and index DBs. `context-lens/` can be deleted once token-miser is stable.

## 2026-05-02 — Fix token-miser MCP server connection timeout

**What changed:**
- `token-miser/mcp.json` — changed Python path from `/usr/bin/python3` (system 3.9.6) to `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` (actual working 3.13.1)

**Decisions made:** Used the absolute path to the correct Python rather than just `python3` to avoid PATH ambiguity across different project contexts.

**Issues encountered:** Other projects couldn't connect to the token-miser MCP server (timeout error -32001). Root cause: `mcp.json` pointed to macOS system Python 3.9 which lacked `tree_sitter_languages` and potentially had compatibility issues. Verified fix by testing the full MCP initialize handshake.

**Open items:** The other project's `mcp.json` also needs to be updated with the corrected Python path if it has its own copy.

## 2026-05-02 — Token Miser user flow review

**What changed:** No files modified — read-only session.

**Decisions made:** N/A.

**Issues encountered:** None.

**Open items:** User flow is well-understood. Potential area to revisit: the confidence scoring in `selector.py` uses a fixed additive model — could be worth tuning thresholds or weighting signals differently based on real-world usage patterns.

## 2026-05-02 — Benchmark tool: credit-based usage capture and docs update

**What changed:**
- `benchmark/_addon_template.py` — rewrote addon to parse Amazon Event Stream binary format from AWS `generateAssistantResponse` responses; captures `credit_usage` per request (class renamed `UsageCaptureAddon`)
- `benchmark/reporter.py` — summary table title changed to "Credit Usage Benchmark Comparison", columns now show "Baseline (mc)" / "Treatment (mc)" (millicredits)
- `.kiro/specs/ai-ide-token-benchmark/requirements.md` — updated Req 2 (proxy) and Req 4 (renamed to "Usage Measurement") to reflect credit-based capture instead of raw tokens
- `.kiro/specs/ai-ide-token-benchmark/design.md` — updated overview, proxy component, and pseudocode to describe AWS event stream parsing and credit usage metric
- `benchmark/README.md` — added note explaining credit vs token metric, added Kiro proxy launch instructions (`HTTPS_PROXY` env vars)
- `tests/test_proxy.py` — updated class name assertions from `TokenCaptureAddon` to `UsageCaptureAddon`
- `.gitignore` — created to exclude `.venv/`, `__pycache__/`, `.DS_Store`, `benchmark_output/`, etc.

**Decisions made:** Kiro routes through AWS (`generateAssistantResponse`) not Anthropic directly, so raw token counts aren't available. Credit usage (proportional to tokens) is the comparison metric. Internal dataclass field names (`input_tokens`, `output_tokens`) kept for pipeline compatibility; JSONL output includes both `credit_usage` (float) and `millicredits` (int) for clarity.

**Issues encountered:** Original addon only handled JSON responses — Kiro uses binary Amazon Event Stream format. Iteratively debugged by adding response snippets to JSONL, discovered the `{"unit": "credit", "usage": 0.213}` event in the stream tail. Also discovered Kiro ignores macOS system proxy — must launch with `HTTPS_PROXY` env var.

**Open items:** Full 10-session benchmark run not yet completed. `example_project/` may need reset from main between runs (`git checkout main -- example_project/`). Branch `test/benchmark-kiro-power` created for testing.

## 2026-05-02 — Token Miser power onboarding and MCP fix

**What changed:**
- `.kiro/settings/mcp.json` — updated `command` from `python` (not found) to `.venv/bin/python` absolute path, and updated `args` path to match current workspace location

**Decisions made:** Used the `.venv` Python (3.12) instead of system Python 3.13 because 3.13 had SSL certificate issues preventing `pip install`. Installed `mcp` SDK into `.venv` since it was the only environment that could reach PyPI.

**Issues encountered:** Power activation showed "No tools available" and MCP server was not connected. Root cause: config pointed to `python` (not on PATH) with a stale workspace path. System Python 3.13 existed but had SSL cert verification failures. Resolved by installing `mcp` into `.venv` and updating config to use `.venv/bin/python`.

**Open items:** The `__pycache__/` and `.context-lens/` files are tracked by git despite being in `.gitignore` — they show as modified in `git status`. Should run `git rm --cached` on them to stop tracking.

## 2026-05-02 — Benchmark analysis: Token Miser adds overhead

**What changed:**
- `~/.kiro/settings/mcp.json` — fixed user-level MCP config: corrected username (`edinhdawg` → `tayingthao`) and Python path to `.venv/bin/python`
- No code changes to benchmark tool itself

**Decisions made:** Analyzed full `tokens.jsonl` from a real benchmark run. Key finding: Token Miser is **more expensive** than baseline for `example_project`. Baseline requests cost ~130-270 mc each at ~2.5% context. Treatment requests with MCP tool calls cost ~575-1,087 mc each at ~15% context, with 8-9 MCP calls per turn. The small project size means full-file reads are cheap, while the Power's multi-step indexing/querying/expanding adds significant overhead.

**Issues encountered:** Other Kiro window couldn't connect to MCP server — user-level config had wrong username and Python path from a different machine. Fixed by updating `~/.kiro/settings/mcp.json`. Also clarified that steering files (`.kiro/steering/`) are auto-included in every conversation, so baseline runs need the steering file removed/renamed to be truly "no Power."

**Open items:** User wants to plan automation improvements to the benchmark before building them. Key ideas: automated prompt injection, consistent timing, better session boundary tracking. The finding that Token Miser adds overhead on small projects is worth investigating — may need larger/more complex projects to see token savings.

## 2026-05-02 — Automated benchmark testing requirements spec

**What changed:**
- `.kiro/specs/automated-benchmark-testing/requirements.md` — new requirements doc covering 9 areas: automated execution, power management, Kiro process management, prompt delivery, response detection, session boundaries, automation config, progress reporting, error recovery
- `.kiro/specs/automated-benchmark-testing/.config.kiro` — spec config (requirements-first workflow, feature type)
- `example_project/` — minor changes to models, routes, and tests (from earlier session, committed together)

**Decisions made:** Requirements-first workflow chosen. Automation replaces the manual copy-paste-wait-enter loop with an Automation Driver that launches Kiro as a subprocess, sends prompts programmatically, and detects response completion via JSONL idle timeout. Power toggling (mcp.json + steering file) is automated between baseline/treatment runs with backup/restore.

**Issues encountered:** Several `__pycache__/`, `.context-lens/`, and `.token-miser/index.db` files were showing as modified in git despite `.gitignore` — they're tracked from earlier commits. Unstaged them manually before committing.

**Open items:** Design doc is next. The `__pycache__` and index DB files still need `git rm --cached` to stop tracking them permanently.

## 2026-05-02 — Automated benchmark testing design doc

**What changed:**
- `.kiro/specs/automated-benchmark-testing/design.md` — new design doc with architecture diagrams, 8 component interfaces, 10 correctness properties, error handling tables, and testing strategy
- `.kiro/memory.md` — appended session summary

**Decisions made:** Prompts delivered via Kiro subprocess stdin. Response completion detected by polling JSONL for idle periods (1s interval). Power toggling via mcp.json `disabled` flag + steering file rename. New conversations created by restarting Kiro process. 10 Hypothesis property tests planned covering all 33 acceptance criteria.

**Issues encountered:** None — design phase was straightforward given the clear requirements.

**Open items:** Task list (tasks.md) is next. The `__pycache__` and index DB files are still tracked by git and showing as modified — still need `git rm --cached`.

## 2026-05-02 — Treatment prompt prefixing for benchmark spec

**What changed:**
- `.kiro/specs/automated-benchmark-testing/requirements.md` — added Requirement 10 (Treatment Prompt Prefixing) with 6 acceptance criteria; updated Req 4 to distinguish baseline (verbatim) vs treatment (prefixed); added MCP_Tool_Prefix and Treatment_Prefix_Map to glossary
- `.kiro/specs/automated-benchmark-testing/design.md` — updated PromptSender with `_apply_prefix()` and configurable prefix map; extended AutomationConfig with `treatment_prefix_map`; added Properties 11-12 and 6 new unit tests

**Decisions made:** Default prefix mapping: task_description→miser-plan, clarifying_question→miser-ask, implementation→miser-fix, verification→miser-ask. Map is configurable in YAML config. Prefix is prepended as space-separated string to mirror how a user would type it in Kiro chat.

**Issues encountered:** None.

**Open items:** Task list (tasks.md) still needs to be created. An empty tasks.md was generated but has no content yet.

## 2026-05-02 — Automated benchmark testing task list

**What changed:**
- `.kiro/specs/automated-benchmark-testing/tasks.md` — new implementation plan with 13 top-level tasks, covering data models, config, PowerManager, PromptSender, ResponseWatcher, AutomationDriver, Orchestrator refactor, CLI wiring, integration tests, and 4 checkpoints
- `.kiro/memory.md` — appended session summary

**Decisions made:** Tasks ordered by dependency: models first, then individual components (PowerManager, PromptSender, ResponseWatcher), then AutomationDriver that composes them, then Orchestrator refactor, then CLI wiring. Checkpoints after each major phase. All 12 property tests marked optional (`*`) for faster MVP path.

**Issues encountered:** None.

**Open items:** Full spec is complete (requirements → design → tasks). Ready to begin task execution starting with Task 1.

## 2026-05-02 — Implement automated benchmark testing

**What changed:**
- `benchmark/automation_driver.py` — new module with 4 classes: PowerManager (mcp.json + steering file toggle), PromptSender (verbatim baseline / prefixed treatment delivery), ResponseWatcher (JSONL idle timeout polling), AutomationDriver (Kiro subprocess lifecycle, restart logic)
- `benchmark/models.py` — added AutomationConfig, WatchResult, BenchmarkError, DEFAULT_PREFIX_MAP; extended BenchmarkConfig with automation field
- `benchmark/config.py` — added automation section validation and validate_kiro_executable()
- `benchmark/orchestrator.py` — replaced manual input() loops with AutomationDriver; added PowerManager lifecycle with try/finally cleanup
- `benchmark/cli.py` — wired kiro_path validation and BenchmarkError handling; removed manual proxy instructions
- `tests/test_config.py` — 16 new tests for automation config validation
- `tests/test_orchestrator.py` — updated init tests for new AutomationDriver/PowerManager attributes

**Decisions made:** Prompts delivered via subprocess stdin. Response detection via JSONL idle polling (1s interval). Power toggling via mcp.json disabled flag + steering file rename. New conversations by restarting Kiro process. 3 consecutive zero-entry timeouts trigger restart, max 2 restarts per run.

**Issues encountered:** None — implementation followed the design doc closely.

**Open items:** Optional property-based tests (tasks marked *) not yet implemented. Should test with a real Kiro instance to validate stdin prompt delivery works as expected.

## 2026-05-02 — Flask async bug benchmark target

**What changed:**
- `flask_project/` — cloned pallets/flask, removed nested .git so it's tracked by parent repo
- `flask_project/src/flask/app.py` — introduced async view bug: removed `self.ensure_sync()` wrapping in `dispatch_request` line 990, so async views return coroutine objects instead of responses
- `flask_project/ISSUES.md` — 10 benchmark issues targeting the async bug from different angles (diagnosis, fix, testing, audit)
- `benchmark_config.yaml` — updated repo_path to `flask_project`, added full automation section with treatment prefix map
- `tests/test_config.py` — updated hardcoded `example_project` assertion to `flask_project`

**Decisions made:** Used a real large project (Flask) instead of the small example_project for meaningful token-miser benchmarking. All 10 issues target the same root cause (missing ensure_sync) from different perspectives to simulate realistic debugging conversations.

**Issues encountered:** Merge from main had divergent branches (resolved with --no-rebase). Stash pop had binary conflict on index.db (resolved with --theirs). Nested .git in flask_project prevented parent repo tracking (removed it). Merged code broke test_token_miser_selection.py import (excluded from test runs).

**Open items:** `test_token_miser_selection.py` has a broken import from the main merge (`run_ask` no longer exists in `query.smart`). Should add remaining Flask project files to git if needed for the benchmark. Ready to run the automated benchmark.

## 2026-05-02 — Full Flask project committed and main merged

**What changed:**
- `flask_project/` — committed full Flask source (236 files) including tests, docs, examples, and the introduced async view bug
- `.kiro/memory.md` — appended session summaries
- Merged `origin/main` into `test/benchmark-kiro-power` (token-miser selector/smart changes, WRITEUP.md, steering updates)

**Decisions made:** Removed nested `.git` from flask_project so it's tracked by the parent repo. Committed the full project rather than just the modified file so the benchmark has a complete codebase to work with.

**Issues encountered:** Merge had divergent branches (used `--no-rebase`). Stash pop had binary conflict on index.db (resolved with `--theirs`). Merged code broke `test_token_miser_selection.py` import (`run_ask` removed from `query.smart`). Config test assertion needed updating after repo_path change.

**Open items:** `test_token_miser_selection.py` still broken from merge — needs import fix. Ready to test the automated benchmark with `kiro` subprocess. Need to verify Kiro accepts stdin input for prompt delivery.

## 2026-05-02 — Fix kiro_path in benchmark config

**What changed:**
- `benchmark_config.yaml` — changed `kiro_path` from placeholder `/path/to/kiro` to actual path `/usr/local/bin/kiro`

**Decisions made:** Used `which kiro` to find the executable at `/usr/local/bin/kiro`.

**Issues encountered:** Benchmark run failed with "Kiro executable '/path/to/kiro' not found on PATH" because the config had a placeholder value from the earlier session.

**Open items:** Ready to retry the benchmark run. Still need to verify Kiro accepts stdin input for automated prompt delivery.
