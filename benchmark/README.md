# AI IDE Token Benchmark

A Python CLI tool that measures and compares credit usage in Kiro IDE under two conditions: **baseline** (no Power active — Kiro sends full file contents to Claude) and **treatment** (Context Lens Power active — Kiro uses compact signature maps plus selective code expansion). The tool runs a transparent HTTPS proxy to capture per-request credit usage from the AWS backend's event stream responses, then produces a comparison report showing per-session reduction ratios and an assessment against the claimed 10–15x reduction target.

> **Note on metrics:** Kiro routes API traffic through AWS (`generateAssistantResponse`) rather than directly to Anthropic. The AWS backend does not expose raw `input_tokens`/`output_tokens` — instead, it reports a per-request **credit usage** value that is proportional to token consumption. The benchmark uses this credit metric for all comparisons. Reduction ratios based on credit usage are equivalent to token-based ratios since the relationship is proportional.

## Prerequisites

- Python 3.10+ (Python 3.12 recommended)
- [mitmproxy](https://mitmproxy.org/) (installed automatically via requirements)
- A working Kiro IDE installation
- The Context Lens Power installed in Kiro (for the treatment run)

## Installation

```bash
# Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install dependencies
.venv/bin/pip install -r benchmark/requirements.txt
```

## Quick Start

### 1. Generate a Session Script

Parse `ISSUES.md` from your target repository and produce a structured session script:

```bash
.venv/bin/python -m benchmark generate --config benchmark_config.yaml
```

This reads `example_project/ISSUES.md`, expands each issue into a 4-turn conversation, and writes the session script to `benchmark_output/session_script.json`.

### 2. Run the Full Benchmark

Execute both baseline and treatment runs in a single invocation:

```bash
.venv/bin/python -m benchmark run --config benchmark_config.yaml
```

The tool will:
1. Start a local HTTPS proxy on the configured port (default: 8080)
2. Guide you through the **baseline run** (no Power active)
3. Guide you through the **treatment run** (Context Lens Power active)
4. Generate usage reports and a comparison report

**Important:** You must launch a separate Kiro IDE window with proxy environment variables so that Kiro's traffic routes through the proxy:

```bash
HTTPS_PROXY=http://localhost:8080 HTTP_PROXY=http://localhost:8080 NODE_TLS_REJECT_UNAUTHORIZED=0 kiro example_project
```

Paste the benchmark prompts into that Kiro window's chat, not the terminal.

### 3. Compare Existing Reports

If you already have baseline and treatment token report JSON files:

```bash
.venv/bin/python -m benchmark report \
    --baseline benchmark_output/baseline_report.json \
    --treatment benchmark_output/treatment_report.json \
    --output-dir benchmark_output \
    --format json
```

## How It Works

1. **Session script generation** — The tool parses `ISSUES.md` from the target repository and creates a structured script of 10 coding sessions, each with 4 turns (task description, clarifying question, implementation, verification). Sessions are labeled as single-file or cross-file based on the number of files involved.

2. **Proxy interception** — A `mitmdump` process runs as a transparent HTTPS proxy. A custom addon intercepts AWS `generateAssistantResponse` responses, parses the Amazon Event Stream binary format, and extracts the per-request credit usage value. It also detects MCP tool calls (`context_index`, `context_query`, `context_expand`) in request bodies. All captured data is written to a JSONL file.

3. **Guided runs** — The orchestrator displays each session and turn prompt via a rich terminal UI. You copy each prompt into Kiro's chat, wait for the response, then press Enter to advance. Between sessions, you start a new Kiro conversation. You do this twice: once with no Power (baseline) and once with Context Lens active (treatment).

4. **Reporting** — After both runs, the tool computes per-session deltas, reduction ratios (baseline / treatment), and an aggregate assessment against the 10–15x claim. The metric is credit usage (proportional to tokens). Results are printed as a summary table and saved to disk.

## Config File Reference

Create a `benchmark_config.yaml` at the repository root:

```yaml
# Path to the target repository containing ISSUES.md
repo_path: "example_project"

# Where to write the generated session script
# Default: "benchmark_output/session_script.json"
prompt_file: "benchmark_output/session_script.json"

# Directory for all output files (reports, JSONL logs)
# Default: "benchmark_output"
output_dir: "benchmark_output"

# Output format for reports: "json" or "csv"
# Default: "json"
output_format: "json"

# Port for the mitmproxy HTTPS proxy
# Default: 8080
proxy_port: 8080

# Timeout in seconds for proxy operations
# Default: 120
timeout_seconds: 120
```

| Parameter | Default | Required | Description |
|---|---|---|---|
| `repo_path` | — | Yes | Path to the target repository |
| `prompt_file` | `benchmark_output/session_script.json` | No | Session script output path |
| `output_dir` | `benchmark_output` | No | Directory for all output files |
| `output_format` | `json` | No | Report format: `json` or `csv` |
| `proxy_port` | `8080` | No | Local proxy port |
| `timeout_seconds` | `120` | No | Proxy operation timeout |

## Output Files

After a full benchmark run, the output directory contains:

| File | Description |
|---|---|
| `session_script.json` | The generated session script with all 10 sessions and their prompts |
| `tokens.jsonl` | Raw JSONL log of all intercepted credit usage and MCP tool calls |
| `baseline_report.json` | Usage report for the baseline run (per-turn and per-session credit usage) |
| `treatment_report.json` | Usage report for the treatment run |
| `comparison_report.json` | Comparison report with deltas, reduction ratios, and assessment |

## Assessment Criteria

The comparison report includes an assessment of the aggregate reduction ratio (based on credit usage):

| Ratio | Assessment |
|---|---|
| ≥ 10.0x | **supported** — falls within the claimed 10–15x range |
| ≥ 5.0x | **partially_supported** — significant reduction but below 10x |
| < 5.0x | **not_supported** — does not support the claimed reduction |

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -x -q
```

This runs all unit tests, property-based tests (via Hypothesis), and integration tests.
