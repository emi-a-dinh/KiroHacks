# Implementation Plan: Automated Benchmark Testing

## Overview

Replace the manual `input()`-driven benchmark orchestration with a fully automated Automation Driver that launches Kiro as a subprocess, delivers prompts via stdin, detects response completion by monitoring proxy JSONL idle periods, manages the token-miser Power state between baseline/treatment runs, and prefixes treatment prompts with MCP tool commands. The implementation touches 5 files: new `automation_driver.py`, modified `orchestrator.py`, extended `models.py`, extended `config.py`, and modified `cli.py`.

## Tasks

- [x] 1. Extend data models with AutomationConfig and BenchmarkError
  - [x] 1.1 Add `DEFAULT_PREFIX_MAP`, `AutomationConfig` dataclass, and `WatchResult` dataclass to `benchmark/models.py`
    - Add `DEFAULT_PREFIX_MAP` dict mapping turn roles to MCP tool prefixes: `task_description` → `miser-plan`, `clarifying_question` → `miser-ask`, `implementation` → `miser-fix`, `verification` → `miser-ask`
    - Add `AutomationConfig` dataclass with fields: `kiro_path` (default `"kiro"`), `idle_timeout` (default `30`), `turn_timeout` (default `300`), `startup_timeout` (default `60`), `treatment_prefix_map` (default from `DEFAULT_PREFIX_MAP`)
    - Add `to_dict()` and `from_dict()` methods on `AutomationConfig` that apply defaults for missing keys
    - Add `WatchResult` dataclass with fields: `entries` (List[dict]), `new_position` (int), `timed_out` (bool)
    - Add `BenchmarkError(Exception)` class for unrecoverable benchmark errors
    - _Requirements: 7.1, 7.2, 10.3_

  - [x] 1.2 Extend `BenchmarkConfig` to include `automation: AutomationConfig` field
    - Add `automation` field with `field(default_factory=AutomationConfig)` to `BenchmarkConfig`
    - Update `BenchmarkConfig.to_dict()` to include `automation` key
    - Update `BenchmarkConfig.from_dict()` to parse `automation` section using `AutomationConfig.from_dict()`, defaulting to `AutomationConfig()` when absent
    - _Requirements: 7.1, 7.2_

  - [ ]* 1.3 Write property test for AutomationConfig parsing with defaults (Property 8)
    - **Property 8: Automation config parsing with defaults**
    - Generate partial automation config dicts with random subsets of keys (including `treatment_prefix_map`). Parse via `AutomationConfig.from_dict()`, assert present values used and missing values get defaults. Serialize via `to_dict()` then parse back, assert equivalence.
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 1.4 Write property test for treatment prefix map config round-trip (Property 12)
    - **Property 12: Treatment prefix map round-trip through config**
    - Generate random prefix map dicts mapping the four turn roles to random non-empty strings. Serialize `AutomationConfig` to dict, parse back, assert `treatment_prefix_map` equivalence. Also test with omitted key to verify defaults.
    - **Validates: Requirements 10.3, 10.4**

- [x] 2. Extend config parser for automation section
  - [x] 2.1 Update `benchmark/config.py` to parse and validate the `automation` YAML section
    - Parse `automation` dict from YAML data and pass to `AutomationConfig.from_dict()`
    - Add validation for automation fields: `idle_timeout`, `turn_timeout`, `startup_timeout` must be positive integers; `kiro_path` must be a non-empty string; `treatment_prefix_map` values must be non-empty strings
    - Update `serialize_config()` to include the `automation` section in YAML output
    - _Requirements: 7.1, 7.2_

  - [x] 2.2 Add `kiro_path` executable validation in config loading
    - Check `shutil.which(kiro_path)` during config validation
    - Emit descriptive error message and halt if Kiro executable not found on PATH
    - _Requirements: 7.4_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement PowerManager
  - [x] 4.1 Create `benchmark/automation_driver.py` with `PowerManager` class
    - Implement `__init__(self, repo_path: str)` that resolves paths to `.kiro/settings/mcp.json` and `.kiro/steering/token-miser.md`
    - Implement `backup()` — reads and stores original contents of both files in memory; raises `FileNotFoundError` for missing MCP config, logs warning for missing steering file
    - Implement `disable_power()` — sets `"disabled": true` in mcp.json for the `token-miser` server entry; renames `token-miser.md` to `token-miser.md.disabled`
    - Implement `enable_power()` — sets `"disabled": false` in mcp.json; restores `token-miser.md` from `.disabled` backup
    - Implement `restore()` — writes original backed-up contents back to both files; catches `OSError` and logs for manual recovery
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 4.2 Write property test for PowerManager backup-restore round-trip (Property 1)
    - **Property 1: PowerManager backup-restore round-trip**
    - Generate random JSON dicts (for mcp.json) and random strings (for steering file). Write to temp files, run `backup()` → any sequence of `disable_power()` / `enable_power()` → `restore()`. Assert file contents match originals.
    - **Validates: Requirements 2.5, 2.6**

  - [ ]* 4.3 Write unit tests for PowerManager disable/enable operations
    - Test `disable_power()` sets `"disabled": true` in mcp.json (Req 2.1)
    - Test `disable_power()` renames steering file to `.disabled` (Req 2.2)
    - Test `enable_power()` sets `"disabled": false` in mcp.json (Req 2.3)
    - Test `enable_power()` restores steering file from `.disabled` (Req 2.4)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 5. Implement PromptSender with treatment prefixing
  - [x] 5.1 Add `PromptSender` class to `benchmark/automation_driver.py`
    - Implement `__init__(self, kiro_process, prefix_map=None)` that stores the process and prefix map (defaulting to `DEFAULT_PREFIX_MAP`)
    - Implement `send(self, prompt, run_type="baseline", role="")` — for baseline: writes prompt + newline to stdin and flushes; for treatment: calls `_apply_prefix()` then writes prefixed prompt + newline
    - Implement `_apply_prefix(self, prompt, role)` — looks up role in prefix_map, returns `"{prefix} {prompt}"`; if role not found, returns prompt verbatim and logs warning
    - Log the applied prefix for each treatment turn
    - Handle `BrokenPipeError` / `OSError` when Kiro process has exited
    - _Requirements: 4.1, 4.4, 4.5, 10.1, 10.2, 10.5, 10.6_

  - [ ]* 5.2 Write property test for verbatim prompt delivery on baseline (Property 2)
    - **Property 2: Verbatim prompt delivery for baseline runs**
    - Generate random strings via `st.text()`. Mock stdin as `io.StringIO`. Call `send(prompt, "baseline", role)`, assert written content equals `prompt + "\n"`.
    - **Validates: Requirements 4.4, 10.2**

  - [ ]* 5.3 Write property test for treatment prompt prefixing (Property 11)
    - **Property 11: Treatment prompt prefixing**
    - Generate random prompt strings and random turn roles from the prefix map. For `run_type="treatment"`, assert output equals `"{prefix} {prompt}\n"`. For `run_type="baseline"`, assert output equals `prompt + "\n"`. Test with both default and custom prefix maps.
    - **Validates: Requirements 10.1, 10.2**

  - [ ]* 5.4 Write unit tests for PromptSender edge cases
    - Test treatment prompt gets correct prefix (Req 10.1)
    - Test baseline prompt has no prefix (Req 10.2)
    - Test default prefix map values match spec (Req 10.3)
    - Test custom prefix map override from config (Req 10.4)
    - Test unknown role delivers prompt verbatim with warning
    - Test prefix is logged for each treatment turn (Req 10.6)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6_

- [x] 6. Implement ResponseWatcher
  - [x] 6.1 Add `ResponseWatcher` class to `benchmark/automation_driver.py`
    - Implement `__init__(self, proxy, idle_timeout, turn_timeout)` storing proxy reference and timeout values
    - Implement `wait_for_response(self, start_position)` — polls `proxy.read_new_entries(start_position)` at 1-second intervals; tracks idle timer (resets on new entries) and turn timer; returns `WatchResult` when idle_timeout exceeded after at least one entry, or when turn_timeout exceeded (with `timed_out=True`)
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ]* 6.2 Write property test for idle timeout response detection (Property 5)
    - **Property 5: Idle timeout response detection**
    - Generate random entry arrival time sequences and positive idle_timeout values. Simulate time progression with mocked `time.time()` and `proxy.read_new_entries()`. Assert completion declared only when idle_timeout exceeded after at least one entry, or turn_timeout exceeded.
    - **Validates: Requirements 5.2**

  - [ ]* 6.3 Write property test for JSONL position tracking (Property 6)
    - **Property 6: JSONL position tracking prevents double-counting**
    - Generate random multi-turn entry sequences with varying counts per turn. Simulate sequential `wait_for_response()` calls. Assert each turn's returned entries are disjoint from previous turns (zero overlap).
    - **Validates: Requirements 5.5**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement AutomationDriver
  - [x] 8.1 Add `AutomationDriver` class to `benchmark/automation_driver.py`
    - Implement `__init__(self, proxy, config)` storing proxy, config, and initializing restart counter and consecutive timeout counter
    - Implement `start_kiro()` — launches `kiro {repo_path}` as subprocess with `HTTPS_PROXY`, `HTTP_PROXY`, `NODE_TLS_REJECT_UNAUTHORIZED=0` env vars; waits up to `startup_timeout` for process to be alive; raises `BenchmarkError` on failure
    - Implement `stop_kiro()` — sends SIGTERM, waits 5s, then SIGKILL if needed (mirrors `ProxyManager.stop()` pattern)
    - Implement `new_conversation()` — stops current Kiro process and starts a new one for clean session context
    - Implement `run_turn(prompt, run_type, role)` — sends prompt via PromptSender, waits via ResponseWatcher, returns entries and timeout flag; tracks consecutive timeouts for restart logic
    - Implement `check_health()` — returns True if Kiro process is still running
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.3, 6.1, 6.2_

  - [x] 8.2 Implement restart logic in AutomationDriver
    - Track consecutive timeout count; restart Kiro after 3 consecutive turns with zero JSONL entries
    - Track total restart count per run; raise `BenchmarkError` after 2 restarts
    - Log restart events including session ID and turn number
    - _Requirements: 9.2, 9.3, 9.4_

  - [ ]* 8.3 Write property test for restart after consecutive unresponsive turns (Property 9)
    - **Property 9: Restart after consecutive unresponsive turns**
    - Generate random boolean sequences (responsive/unresponsive turns). Mock AutomationDriver internals. Assert restart triggered iff 3 consecutive unresponsive turns. Assert a responsive turn resets the counter.
    - **Validates: Requirements 9.2**

  - [ ]* 8.4 Write property test for maximum restart limit (Property 10)
    - **Property 10: Maximum restart limit per run**
    - Generate scenarios requiring 0-5 restarts. Assert `BenchmarkError` raised on 3rd restart attempt (after 2 successful restarts).
    - **Validates: Requirements 9.4**

  - [ ]* 8.5 Write unit tests for AutomationDriver process management
    - Test `start_kiro()` passes correct env vars (Req 3.1)
    - Test `start_kiro()` passes repo_path as workspace argument (Req 3.2)
    - Test `stop_kiro()` sends SIGTERM then waits (Req 3.4)
    - Test unexpected Kiro exit logs error (Req 3.5)
    - Test startup timeout halts with error (Req 3.6)
    - Test turn timeout continues to next turn (Req 5.4)
    - Test timed-out turn records zero credit usage (Req 9.1)
    - Test restart logs session and turn number (Req 9.3)
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 5.4, 9.1, 9.3_

- [x] 9. Refactor Orchestrator for automated execution
  - [x] 9.1 Modify `benchmark/orchestrator.py` to use AutomationDriver instead of manual `input()` loops
    - Replace `input()` calls and rich Panel prompts with `AutomationDriver.run_turn()` calls
    - Pass `run_type` and `turn.role` to `run_turn()` so PromptSender applies correct prefix logic
    - Call `automation_driver.new_conversation()` between sessions
    - Create `PowerManager` and `AutomationDriver` instances in `run_benchmark()`
    - Call `power_manager.backup()` at start, `disable_power()` before baseline, `enable_power()` before treatment
    - Wrap in `try/finally` to guarantee `power_manager.restore()` and `automation_driver.stop_kiro()`
    - Write partial reports on error before exiting
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 6.1, 6.3, 9.5, 9.6_

  - [x] 9.2 Add progress reporting to Orchestrator
    - Print progress line after each turn: run type, session number, turn number, credit usage (Req 8.1)
    - Print session summary line after each session with aggregate credit usage (Req 8.2)
    - Print total credit usage after each run completes (Req 8.3)
    - Print warning line for timed-out turns (Req 8.4)
    - Log resolved automation configuration at run start (Req 7.3)
    - _Requirements: 7.3, 8.1, 8.2, 8.3, 8.4_

  - [ ]* 9.3 Write property test for prompt delivery ordering (Property 3)
    - **Property 3: Prompt delivery ordering**
    - Generate random SessionScripts with 1-5 sessions, 1-4 turns each. Mock AutomationDriver. Assert prompts delivered in strictly ascending session_id then turn_number order.
    - **Validates: Requirements 4.2**

  - [ ]* 9.4 Write property test for sequential prompt-response discipline (Property 4)
    - **Property 4: Sequential prompt-response discipline**
    - Generate random multi-turn sessions. Mock ResponseWatcher with variable delays. Assert each `send()` call happens only after previous `wait_for_response()` returns.
    - **Validates: Requirements 4.3**

  - [ ]* 9.5 Write property test for session boundary new conversations (Property 7)
    - **Property 7: Session boundary new conversations**
    - Generate SessionScripts with 1-10 sessions. Mock AutomationDriver. Assert `new_conversation()` called exactly N-1 times for N sessions, and zero times within a session.
    - **Validates: Requirements 6.1**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Update CLI to wire automation driver
  - [x] 11.1 Modify `benchmark/cli.py` `cmd_run()` to use the automated flow
    - Remove manual proxy instruction printing (`print_proxy_instructions`)
    - Wire up `AutomationDriver` and `PowerManager` through the `Orchestrator`
    - Check `shutil.which(config.automation.kiro_path)` before starting proxy; halt with descriptive error if not found
    - Print the Comparison_Report summary table to stdout on completion
    - _Requirements: 1.1, 1.3, 7.4_

  - [ ]* 11.2 Write unit tests for CLI automation wiring
    - Test `cmd_run()` halts early if kiro_path not found (Req 7.4)
    - Test `cmd_run()` produces comparison report on completion (Req 1.3)
    - _Requirements: 1.3, 7.4_

- [x] 12. Integration testing
  - [ ]* 12.1 Write integration test with mock Kiro process
    - Create a mock Kiro script that reads stdin and writes predictable JSONL entries
    - Test full benchmark run: both baseline and treatment complete, reports generated, power state toggled correctly
    - Verify treatment prompts are prefixed and baseline prompts are verbatim
    - Test partial report written on error
    - Test power state restored on error
    - _Requirements: 1.1, 1.2, 1.3, 2.5, 9.5, 9.6, 10.1, 10.2_

  - [ ]* 12.2 Write integration test for baseline-to-treatment transition
    - Verify stop → reconfigure power → start sequence during run transition
    - _Requirements: 3.3, 6.3_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 12 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses Python throughout — all code examples and implementations use Python
- The existing modules (`proxy.py`, `session_script.py`, `reporter.py`) remain unchanged
- All new code goes in `benchmark/automation_driver.py` with modifications to `models.py`, `config.py`, `orchestrator.py`, and `cli.py`
