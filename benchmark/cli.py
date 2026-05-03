"""CLI entry point for the AI IDE Token Benchmark.

Provides three subcommands:
  generate  — Generate a session script from ISSUES.md
  run       — Run the full benchmark (baseline + treatment)
  report    — Compare two existing Token_Report JSON files
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from benchmark.config import load_config, validate_kiro_executable
from benchmark.models import BenchmarkError, RunRecord
from benchmark.orchestrator import Orchestrator
from benchmark.proxy import ProxyManager
from benchmark.reporter import (
    generate_comparison_report,
    print_summary_table,
    write_comparison_report,
    write_token_report,
)
from benchmark.session_script import (
    generate_session_script,
    parse_issues_md,
    parse_session_script,
    write_session_script,
)


# ---------------------------------------------------------------------------
# 7.1  Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands.

    Returns:
        An ArgumentParser with ``generate``, ``run``, and ``report``
        subparsers.
    """
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="AI IDE Token Benchmark — measure and compare token consumption in Kiro IDE.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- generate ---
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate a session script from ISSUES.md",
    )
    gen_parser.add_argument(
        "--config",
        required=True,
        help="Path to the benchmark YAML config file",
    )

    # --- run ---
    run_parser = subparsers.add_parser(
        "run",
        help="Run the full benchmark (baseline + treatment)",
    )
    run_parser.add_argument(
        "--config",
        required=True,
        help="Path to the benchmark YAML config file",
    )

    # --- report ---
    report_parser = subparsers.add_parser(
        "report",
        help="Compare two existing Token_Report JSON files",
    )
    report_parser.add_argument(
        "--baseline",
        required=True,
        help="Path to the baseline Token_Report JSON file",
    )
    report_parser.add_argument(
        "--treatment",
        required=True,
        help="Path to the treatment Token_Report JSON file",
    )
    report_parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write the comparison report (optional)",
    )
    report_parser.add_argument(
        "--format",
        default="json",
        choices=["json", "csv"],
        help="Output format for the comparison report (default: json)",
    )

    return parser


# ---------------------------------------------------------------------------
# 7.3  generate command
# ---------------------------------------------------------------------------


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate a session script from ISSUES.md and write it to disk.

    Args:
        args: Parsed CLI arguments (must include ``config``).
    """
    config = load_config(args.config)
    issues = parse_issues_md(os.path.join(config.repo_path, "ISSUES.md"))
    script = generate_session_script(issues, config.repo_path)
    write_session_script(script, config.prompt_file)
    print(f"Session script written to {config.prompt_file}")
    print(f"  Sessions: {len(script.sessions)}")
    print(f"  Total turns: {sum(len(s.turns) for s in script.sessions)}")


# ---------------------------------------------------------------------------
# 7.4  run command
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Run the full benchmark: generate/load script, proxy, orchestrate, report.

    Args:
        args: Parsed CLI arguments (must include ``config``).
    """
    config = load_config(args.config)

    # Validate Kiro executable before starting proxy
    validate_kiro_executable(config)

    # Generate or load session script
    if os.path.exists(config.prompt_file):
        with open(config.prompt_file) as f:
            script = parse_session_script(f.read())
        print(f"Loaded existing session script: {config.prompt_file}")
    else:
        issues = parse_issues_md(os.path.join(config.repo_path, "ISSUES.md"))
        script = generate_session_script(issues, config.repo_path)
        write_session_script(script, config.prompt_file)
        print(f"Generated session script: {config.prompt_file}")

    # Set up proxy
    jsonl_path = os.path.join(config.output_dir, "tokens.jsonl")
    proxy = ProxyManager(port=config.proxy_port, jsonl_path=jsonl_path)

    # Start proxy
    try:
        proxy.start()
        print(f"Proxy started on port {config.proxy_port}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Install mitmproxy: .venv/bin/pip install mitmproxy")
        raise SystemExit(1)

    try:
        # Run benchmark
        orchestrator = Orchestrator(script, proxy, config)
        baseline, treatment = orchestrator.run_benchmark()

        # Write reports
        write_token_report(baseline, config.output_dir, config.output_format)
        write_token_report(treatment, config.output_dir, config.output_format)

        # Generate and write comparison
        comparison = generate_comparison_report(baseline, treatment)
        write_comparison_report(comparison, config.output_dir, config.output_format)

        # Print summary
        print_summary_table(comparison)

        print(f"\nReports written to {config.output_dir}/")
    except BenchmarkError as e:
        print(f"Error: {e}")
        raise SystemExit(1)
    finally:
        proxy.stop()
        print("Proxy stopped.")


# ---------------------------------------------------------------------------
# 7.5  report command
# ---------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> None:
    """Compare two existing Token_Report JSON files and print a summary.

    Args:
        args: Parsed CLI arguments (must include ``baseline`` and
            ``treatment``).
    """
    # Load two existing Token_Report JSON files
    with open(args.baseline) as f:
        baseline = RunRecord.from_dict(json.load(f))
    with open(args.treatment) as f:
        treatment = RunRecord.from_dict(json.load(f))

    # Generate comparison
    comparison = generate_comparison_report(baseline, treatment)

    # Write if output dir specified
    if args.output_dir:
        write_comparison_report(comparison, args.output_dir, args.format)
        print(f"Comparison report written to {args.output_dir}/")

    # Print summary
    print_summary_table(comparison)


# ---------------------------------------------------------------------------
# 7.1 / 7.2  main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "generate": cmd_generate,
        "run": cmd_run,
        "report": cmd_report,
    }

    commands[args.command](args)
