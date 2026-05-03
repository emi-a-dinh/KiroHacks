# Design Document

## Overview

The AI IDE Token Benchmark is a Python CLI tool that measures credit usage in Kiro IDE across two conditions — baseline (no Power) vs. treatment (Context Lens Power active) — using a transparent mitmproxy-based HTTPS proxy to capture per-request credit usage from the AWS backend's event stream responses. Credit usage is proportional to token consumption and serves as the comparison metric since Kiro's AWS backend does not expose raw token counts.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Benchmark CLI                             │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐ │
│  │  Config   │  │   Session    │  │Orchestr- │  │Reporter │ │
│  │  Loader   │  │   Script     │  │  ator    │  │         │ │
│  │          │  │  Generator   │  │          │  │         │ │
│  └────┬─────┘  └──────┬───────┘  └────┬─────┘  └────┬────┘ │
│       │               │               │              │      │
│       └───────────────┼───────────────┼──────────────┘      │
│                       │               │                      │
│                       ▼               ▼                      │
│              ┌─────────────────────────────┐                 │
│              │      Token Collector        │                 │
│              │  (shared queue from proxy)  │                 │
│              └────────────┬────────────────┘                 │
└───────────────────────────┼──────────────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │   mitmproxy (mitmdump)   │
              │   TokenCaptureAddon      │
              │                          │
              │  localhost:8080          │
              └──────────┬───────────────┘
                         │
            ┌────────────┼────────────────┐
            │            │                │
            ▼            ▼                ▼
     ┌──────────┐  ┌──────────┐   ┌──────────────┐
     │  Kiro    │  │ Claude   │   │  MCP Tools   │
     │  IDE     │→ │  API     │   │  (Context    │
     │          │  │(Anthropic)│   │   Lens)      │
     └──────────┘  └──────────┘   └──────────────┘
```

## Component Breakdown

### 1. Config Loader (`config.py`)
- Loads YAML config file
- Validates required fields, applies defaults
- Round-trip serialization support

### 2. Session Script Generator (`session_script.py`)
- Parses `example_project/ISSUES.md` using regex to extract issue metadata
- Expands each issue into a 4-turn session
- Labels sessions as single-file or cross-file based on file count
- Writes JSON prompt file with schema validation

### 3. Proxy / Token Capture (`proxy.py`)
- Runs `mitmdump` as a subprocess with a custom addon script
- Addon intercepts AWS `generateAssistantResponse` responses in Amazon Event Stream binary format
- Addon parses the binary event stream to extract per-request credit usage (`{"unit": "credit", "usage": 0.213}`) and context usage percentage
- Since raw `input_tokens`/`output_tokens` are not exposed by the AWS backend, credit usage (×1000) is stored as `input_tokens` for reporting compatibility
- Addon inspects request bodies for MCP tool calls (`context_index`, `context_query`, `context_expand`)
- Writes captured data to a JSONL temp file that the orchestrator reads

### 4. Orchestrator (`orchestrator.py`)
- Drives the benchmark flow: baseline run → treatment run
- Displays current session/turn to the user via rich terminal UI
- Waits for user input (Enter to advance, signals for session boundaries)
- Reads token data from the proxy's JSONL output after each turn
- Collects all turn records into a RunRecord

### 5. Reporter (`reporter.py`)
- Generates Token_Report (per-run) in JSON and CSV
- Generates Comparison_Report with deltas, reduction ratios, and 10–15x assessment
- Prints summary table to stdout using rich

### 6. Data Models (`models.py`)
- Pure dataclasses, no external dependencies

## Data Models

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Turn:
    turn_number: int
    role: str          # "task_description" | "clarifying_question" | "implementation" | "verification"
    prompt: str

@dataclass
class Session:
    session_id: int
    issue_number: int
    title: str
    task_type: str     # "single-file" | "cross-file"
    files: List[str]
    turns: List[Turn]

@dataclass
class SessionScript:
    generated_at: str
    repo_path: str
    sessions: List[Session]

@dataclass
class TokenCount:
    input_tokens: int
    output_tokens: int
    total_tokens: int

@dataclass
class TurnRecord:
    session_id: int
    turn_number: int
    tokens: TokenCount
    mcp_tools_called: List[str] = field(default_factory=list)

@dataclass
class SessionRecord:
    session_id: int
    task_type: str
    turns: List[TurnRecord]
    aggregate: TokenCount

@dataclass
class RunRecord:
    run_type: str      # "baseline" | "treatment"
    timestamp: str
    prompt_file: str
    sessions: List[SessionRecord]
    aggregate: TokenCount

@dataclass
class SessionComparison:
    session_id: int
    task_type: str
    baseline: TokenCount
    treatment: TokenCount
    delta: TokenCount
    reduction_ratio: float  # baseline.total / treatment.total

@dataclass
class ComparisonReport:
    timestamp: str
    sessions: List[SessionComparison]
    aggregate_baseline: TokenCount
    aggregate_treatment: TokenCount
    aggregate_delta: TokenCount
    aggregate_reduction_ratio: float
    assessment: str    # "supported" | "partially_supported" | "not_supported"

@dataclass
class BenchmarkConfig:
    repo_path: str
    prompt_file: str = "benchmark_output/session_script.json"
    output_dir: str = "benchmark_output"
    output_format: str = "json"   # "json" | "csv"
    proxy_port: int = 8080
    timeout_seconds: int = 120
```

## Session Script Generation Algorithm

```
1. Read example_project/ISSUES.md as raw text
2. Split on "## Issue N" headers using regex: r'^## Issue (\d+)\s*—\s*(.+)$'
3. For each issue block:
   a. Extract issue_number and title from header
   b. Extract files from **File:** or **Files:** line
      - Single **File:** → ["path"] → task_type = "single-file"
      - **Files:** with comma-separated paths → ["path1", "path2"] → task_type = "cross-file"
   c. Extract the LLM prompt from the blockquote (> "...")
   d. Generate 4 turns:
      Turn 1 (task_description): The extracted LLM prompt verbatim
      Turn 2 (clarifying_question): "Can you show me the current code in {files} so I can understand what needs to change?"
      Turn 3 (implementation): "Go ahead and make the changes. {issue-specific detail}"
      Turn 4 (verification): "Does this look correct? Are there any edge cases we should handle?"
4. Assemble into SessionScript dataclass
5. Serialize to JSON, validate against schema
6. Write to output_dir/session_script.json
```

## Proxy Interception Flow

### Addon Script (`_addon.py` — written to temp dir at runtime)

```python
# Simplified pseudocode for the mitmproxy addon
import json, struct

class TokenCaptureAddon:
    def __init__(self, output_path):
        self.output_path = output_path
        self.log_file = open(output_path, "a")

    def response(self, flow):
        if "amazonaws.com" not in flow.request.host:
            return
        content_type = flow.response.headers.get("content-type", "")
        if "amazon.eventstream" not in content_type:
            return
        # Parse binary Amazon Event Stream format
        events = parse_eventstream(flow.response.content)
        for headers, payload in events:
            data = json.loads(payload)
            # Credit usage event: {"unit": "credit", "usage": 0.213}
            if "usage" in data and "unit" in data:
                entry = {
                    "type": "token_usage",
                    "input_tokens": int(data["usage"] * 1000),
                    "output_tokens": 0,
                    "credit_usage": data["usage"],
                    "timestamp": time.time()
                }
                self.log_file.write(json.dumps(entry) + "\n")
                self.log_file.flush()

    def request(self, flow):
        if "amazonaws.com" not in flow.request.host:
            return
        content = flow.request.content.decode("utf-8", errors="replace")
        tools_found = [t for t in ["context_index", "context_query", "context_expand"] if t in content]
        if tools_found:
            entry = {"type": "mcp_tool_call", "tools": tools_found, "timestamp": time.time()}
            self.log_file.write(json.dumps(entry) + "\n")
            self.log_file.flush()
```

### Proxy Lifecycle

```
1. Orchestrator writes addon script to temp file
2. Orchestrator starts mitmdump subprocess:
   mitmdump --listen-port 8080 --scripts /tmp/addon.py --set output=/tmp/tokens.jsonl
3. Orchestrator prints proxy setup instructions to user
4. User configures system proxy → localhost:8080
5. During benchmark: addon writes JSONL entries as traffic flows
6. After each turn: orchestrator reads new lines from JSONL file
7. After run completes: orchestrator kills mitmdump subprocess
8. Orchestrator parses all JSONL entries into TurnRecords
```

## Run Orchestration Flow

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Load Config │
                    └──────┬──────┘
                           │
                    ┌──────▼──────────┐
                    │ Generate Session│
                    │ Script (or load)│
                    └──────┬──────────┘
                           │
                    ┌──────▼──────┐
                    │ Start Proxy │
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │   BASELINE RUN          │
              │                         │
              │  "Disable all Powers"   │
              │  [wait for confirm]     │
              │                         │
              │  For each session:      │
              │    "Start new chat"     │
              │    For each turn:       │
              │      Display prompt     │
              │      [wait for Enter]   │
              │      Read proxy JSONL   │
              │      Record TurnRecord  │
              │                         │
              │  Save baseline report   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │   TREATMENT RUN         │
              │                         │
              │  "Enable Context Lens"  │
              │  [wait for confirm]     │
              │                         │
              │  For each session:      │
              │    "Start new chat"     │
              │    For each turn:       │
              │      Display prompt     │
              │      [wait for Enter]   │
              │      Read proxy JSONL   │
              │      Record TurnRecord  │
              │                         │
              │  Save treatment report  │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Generate Comparison    │
              │  Report + Print Summary │
              └────────────┬────────────┘
                           │
                    ┌──────▼──────┐
                    │ Stop Proxy  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    DONE     │
                    └─────────────┘
```

## Report Generation Logic

### Token_Report (per run)

```json
{
  "run_type": "baseline",
  "timestamp": "2026-05-02T15:30:00Z",
  "prompt_file": "benchmark_output/session_script.json",
  "sessions": [
    {
      "session_id": 1,
      "task_type": "single-file",
      "turns": [
        {
          "turn_number": 1,
          "input_tokens": 1842,
          "output_tokens": 317,
          "total_tokens": 2159,
          "mcp_tools_called": []
        }
      ],
      "session_input_tokens": 7200,
      "session_output_tokens": 1100,
      "session_total_tokens": 8300
    }
  ],
  "run_input_tokens": 72000,
  "run_output_tokens": 11000,
  "run_total_tokens": 83000
}
```

### Comparison_Report

```json
{
  "timestamp": "2026-05-02T16:00:00Z",
  "sessions": [
    {
      "session_id": 1,
      "task_type": "single-file",
      "baseline_total": 8300,
      "treatment_total": 2100,
      "delta": -6200,
      "reduction_ratio": 3.95
    }
  ],
  "aggregate": {
    "baseline_total": 83000,
    "treatment_total": 7500,
    "delta": -75500,
    "reduction_ratio": 11.07
  },
  "assessment": "supported",
  "assessment_detail": "Aggregate reduction ratio of 11.07x falls within the claimed 10-15x range."
}
```

### Assessment Logic

```python
def assess_reduction(ratio: float) -> tuple[str, str]:
    if ratio >= 10.0:
        return "supported", f"Aggregate reduction ratio of {ratio:.2f}x falls within the claimed 10-15x range."
    elif ratio >= 5.0:
        return "partially_supported", f"Aggregate reduction ratio of {ratio:.2f}x shows significant reduction but falls below the claimed 10x minimum."
    else:
        return "not_supported", f"Aggregate reduction ratio of {ratio:.2f}x does not support the claimed 10-15x reduction."
```

### CSV Format

```csv
session_id,task_type,baseline_input,baseline_output,baseline_total,treatment_input,treatment_output,treatment_total,delta_input,delta_output,delta_total,reduction_ratio
1,single-file,5800,1400,7200,1500,600,2100,-4300,-800,-5100,3.43
2,cross-file,12000,2200,14200,900,300,1200,-11100,-1900,-13000,11.83
...
AGGREGATE,,72000,11000,83000,6000,1500,7500,-66000,-9500,-75500,11.07
```

## Config File Schema (YAML)

```yaml
# benchmark_config.yaml
repo_path: "example_project"
prompt_file: "benchmark_output/session_script.json"
output_dir: "benchmark_output"
output_format: "json"    # "json" or "csv"
proxy_port: 8080
timeout_seconds: 120
```

### Defaults

| Parameter | Default | Required |
|---|---|---|
| `repo_path` | — | Yes |
| `prompt_file` | `{output_dir}/session_script.json` | No |
| `output_dir` | `benchmark_output` | No |
| `output_format` | `json` | No |
| `proxy_port` | `8080` | No |
| `timeout_seconds` | `120` | No |

## File Structure

```
benchmark/
├── __init__.py
├── __main__.py          # Entry point: python -m benchmark
├── cli.py               # Argument parsing, top-level commands
├── config.py            # BenchmarkConfig dataclass + YAML loader
├── models.py            # All data model dataclasses
├── session_script.py    # ISSUES.md parser + session script generator
├── proxy.py             # mitmproxy subprocess management + addon generation
├── orchestrator.py      # Run orchestration + terminal UI
├── reporter.py          # Token_Report + Comparison_Report generation
└── _addon_template.py   # Template for the mitmproxy addon script

tests/
├── test_models.py       # Existing tests
├── test_config.py       # Config round-trip property tests
├── test_session_script.py  # Session script generation + round-trip tests
├── test_reporter.py     # Aggregation + comparison correctness tests
└── test_proxy.py        # Addon parsing tests (unit tests, no live proxy)
```

## Property-Based Test Strategy

### 1. Session Script Round-Trip (Req 1, AC 7)
```
For any valid SessionScript s:
  parse(serialize(s)) == s
```
Generate arbitrary SessionScript instances with hypothesis. Serialize to JSON, parse back, assert equality.

### 2. Config Round-Trip (Req 7, AC 5)
```
For any valid BenchmarkConfig c:
  parse(serialize(c)) == c
```
Generate arbitrary BenchmarkConfig instances. Serialize to YAML, parse back, assert equality.

### 3. Token Aggregation (Req 4, AC 5-6)
```
For any RunRecord r:
  for each session s in r.sessions:
    sum(t.tokens.input_tokens for t in s.turns) == s.aggregate.input_tokens
    sum(t.tokens.output_tokens for t in s.turns) == s.aggregate.output_tokens
    sum(t.tokens.total_tokens for t in s.turns) == s.aggregate.total_tokens
  sum(s.aggregate.total_tokens for s in r.sessions) == r.aggregate.total_tokens
```
Generate arbitrary RunRecords with hypothesis. Compute aggregates via reporter, verify sums.

### 4. Comparison Delta (Req 6, AC 7)
```
For any SessionComparison sc:
  sc.delta.input_tokens == sc.treatment.input_tokens - sc.baseline.input_tokens
  sc.delta.output_tokens == sc.treatment.output_tokens - sc.baseline.output_tokens
  sc.delta.total_tokens == sc.treatment.total_tokens - sc.baseline.total_tokens
```

### 5. Reduction Ratio (Req 6, AC 8)
```
For any SessionComparison sc where sc.treatment.total_tokens > 0:
  sc.reduction_ratio == sc.baseline.total_tokens / sc.treatment.total_tokens
```

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `mitmproxy` | `>=10.0` | HTTPS proxy for intercepting Claude API traffic |
| `rich` | `>=13.0` | Terminal UI: tables, progress, prompts |
| `pyyaml` | `>=6.0` | Config file parsing |
| `hypothesis` | `>=6.0` | Property-based testing |
| `pytest` | `>=7.0` | Test runner |

## Requirement Traceability

| Requirement | Components |
|---|---|
| Req 1: Session Script Generation | `session_script.py`, `models.py` |
| Req 2: Proxy Interception | `proxy.py`, `_addon_template.py` |
| Req 3: Run Orchestration | `orchestrator.py`, `cli.py` |
| Req 4: Usage Measurement | `proxy.py`, `orchestrator.py`, `models.py` |
| Req 5: Results Storage | `reporter.py` |
| Req 6: Comparison Report | `reporter.py` |
| Req 7: Run Configuration | `config.py` |
