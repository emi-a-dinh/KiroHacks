# Implementation Tasks

## Task 1: Project scaffolding and data models
- [x] 1.1 Create `benchmark/` directory with `__init__.py` and `__main__.py` entry point
- [x] 1.2 Create `benchmark/models.py` with all dataclasses: `Turn`, `Session`, `SessionScript`, `TokenCount`, `TurnRecord`, `SessionRecord`, `RunRecord`, `SessionComparison`, `ComparisonReport`, `BenchmarkConfig`
- [x] 1.3 Add `to_dict()` and `from_dict()` methods to all dataclasses for JSON serialization
- [x] 1.4 Create `benchmark/requirements.txt` with dependencies: `mitmproxy>=10.0`, `rich>=13.0`, `pyyaml>=6.0`, `hypothesis>=6.0`, `pytest>=7.0`

## Task 2: Config loader
- [x] 2.1 Create `benchmark/config.py` with `load_config(path: str) -> BenchmarkConfig` that reads YAML, validates required fields (`repo_path`), and applies defaults
- [x] 2.2 Add `serialize_config(config: BenchmarkConfig) -> str` for YAML round-trip serialization
- [x] 2.3 Add validation: emit descriptive error and raise `SystemExit` if required params missing or invalid values
- [x] 2.4 Create `benchmark_config.yaml` example config file at repo root

## Task 3: Session script generator
- [x] 3.1 Create `benchmark/session_script.py` with `parse_issues_md(path: str) -> List[dict]` that parses `ISSUES.md` using regex to extract issue number, title, files, and LLM prompt
- [x] 3.2 Add `generate_session_script(issues: List[dict], repo_path: str) -> SessionScript` that expands each issue into a 4-turn session with task_type labeling (single-file vs cross-file)
- [x] 3.3 Add `serialize_session_script(script: SessionScript) -> str` and `parse_session_script(json_str: str) -> SessionScript` for JSON round-trip
- [x] 3.4 Add JSON schema validation for the session script format
- [x] 3.5 Add `write_session_script(script: SessionScript, output_path: str)` that creates output dir if needed and writes the JSON file

## Task 4: Proxy interception
- [x] 4.1 Create `benchmark/_addon_template.py` with the mitmproxy addon class `TokenCaptureAddon` that intercepts Anthropic API responses and extracts `usage.input_tokens` / `usage.output_tokens` to JSONL
- [x] 4.2 Add MCP tool call detection in the addon's `request()` method — inspect request body for `context_index`, `context_query`, `context_expand` and log to JSONL
- [x] 4.3 Create `benchmark/proxy.py` with `ProxyManager` class that writes the addon to a temp file, starts `mitmdump` as a subprocess, and provides `start()` / `stop()` / `read_entries()` methods
- [x] 4.4 Add proxy setup instruction printing (tells user how to configure system proxy to localhost:PORT)

## Task 5: Run orchestrator
- [x] 5.1 Create `benchmark/orchestrator.py` with `Orchestrator` class that takes a `SessionScript`, `ProxyManager`, and `BenchmarkConfig`
- [x] 5.2 Implement `run_single(run_type: str) -> RunRecord` that guides user through all sessions/turns for one run condition, displaying prompts via rich and waiting for Enter after each turn
- [x] 5.3 Implement session boundary handling: instruct user to start a new Kiro chat between sessions
- [x] 5.4 Implement `run_benchmark() -> (RunRecord, RunRecord)` that orchestrates baseline then treatment, with condition setup prompts and user confirmation
- [x] 5.5 Add JSONL reading after each turn to collect token data from the proxy into `TurnRecord` objects
- [x] 5.6 Compute session and run aggregates from turn-level token counts

## Task 6: Reporter
- [x] 6.1 Create `benchmark/reporter.py` with `generate_token_report(run: RunRecord) -> str` that produces JSON output matching the Token_Report schema
- [x] 6.2 Add `generate_token_report_csv(run: RunRecord) -> str` for CSV output
- [x] 6.3 Add `generate_comparison_report(baseline: RunRecord, treatment: RunRecord) -> ComparisonReport` that computes per-session deltas, reduction ratios, and the 10–15x assessment
- [x] 6.4 Add `print_summary_table(report: ComparisonReport)` using rich to print a formatted comparison table to stdout
- [x] 6.5 Add `write_comparison_report(report: ComparisonReport, output_dir: str, format: str)` for JSON and CSV file output

## Task 7: CLI entry point
- [x] 7.1 Create `benchmark/cli.py` with argument parsing: `generate` (session script only), `run` (full benchmark), `report` (compare two existing report files)
- [x] 7.2 Wire `benchmark/__main__.py` to call `cli.main()`
- [x] 7.3 Implement `generate` command: load config → generate session script → write to file
- [x] 7.4 Implement `run` command: load config → generate/load session script → start proxy → orchestrate baseline + treatment → generate reports
- [x] 7.5 Implement `report` command: load two Token_Report JSON files → generate comparison report → print summary

## Task 8: Property-based tests
- [x] 8.1 Create `tests/test_session_script.py` with hypothesis test for session script JSON round-trip: `parse(serialize(s)) == s` for arbitrary `SessionScript` instances
- [x] 8.2 Create `tests/test_config.py` with hypothesis test for config YAML round-trip: `parse(serialize(c)) == c` for arbitrary `BenchmarkConfig` instances
- [x] 8.3 Create `tests/test_reporter.py` with hypothesis test for token aggregation correctness: `sum(turn.total) == session.total` and `sum(session.total) == run.total`
- [x] 8.4 Add hypothesis test for comparison delta correctness: `delta == treatment - baseline` for each metric
- [x] 8.5 Add hypothesis test for reduction ratio correctness: `ratio == baseline / treatment` for each metric (where treatment > 0)

## Task 9: Integration test and documentation
- [x] 9.1 Create `tests/test_integration.py` with an end-to-end test that generates a session script from `example_project/ISSUES.md` and validates the output structure (10 sessions, 4 turns each, correct labels)
- [x] 9.2 Add a test that generates a Token_Report from mock data, then generates a Comparison_Report, and verifies all correctness properties hold
- [x] 9.3 Add `benchmark/README.md` with usage instructions: install deps, create config, generate script, run benchmark, interpret results
