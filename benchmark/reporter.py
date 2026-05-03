"""Reporter module for the AI IDE Token Benchmark.

Generates Token_Report (per-run) in JSON and CSV formats, produces
Comparison_Report with deltas, reduction ratios, and 10–15x assessment,
and prints summary tables using rich.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Dict

from rich.console import Console
from rich.table import Table

from benchmark.models import (
    ComparisonReport,
    RunRecord,
    SessionComparison,
    TokenCount,
)


console = Console()


# ---------------------------------------------------------------------------
# 6.1  generate_token_report
# ---------------------------------------------------------------------------


def generate_token_report(run: RunRecord) -> str:
    """Produce a JSON string matching the Token_Report schema.

    The output includes per-turn token counts, per-session aggregates,
    and overall run aggregates.

    Args:
        run: A RunRecord containing all session and turn data.

    Returns:
        A JSON string (indented) representing the Token_Report.
    """
    return json.dumps(run.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# 6.2  generate_token_report_csv
# ---------------------------------------------------------------------------


def generate_token_report_csv(run: RunRecord) -> str:
    """Produce a CSV string for a Token_Report.

    Columns: session_id, task_type, turn_number, input_tokens,
    output_tokens, total_tokens, mcp_tools_called

    One row per turn, plus a summary row per session (turn_number="TOTAL"),
    plus a final AGGREGATE row.

    Args:
        run: A RunRecord containing all session and turn data.

    Returns:
        A CSV-formatted string with header row.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "session_id",
        "task_type",
        "turn_number",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "mcp_tools_called",
    ])

    for session in run.sessions:
        for turn in session.turns:
            writer.writerow([
                session.session_id,
                session.task_type,
                turn.turn_number,
                turn.tokens.input_tokens,
                turn.tokens.output_tokens,
                turn.tokens.total_tokens,
                ";".join(turn.mcp_tools_called),
            ])
        # Session TOTAL row
        writer.writerow([
            session.session_id,
            session.task_type,
            "TOTAL",
            session.aggregate.input_tokens,
            session.aggregate.output_tokens,
            session.aggregate.total_tokens,
            "",
        ])

    # AGGREGATE row
    writer.writerow([
        "AGGREGATE",
        "",
        "",
        run.aggregate.input_tokens,
        run.aggregate.output_tokens,
        run.aggregate.total_tokens,
        "",
    ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# 6.3  generate_comparison_report
# ---------------------------------------------------------------------------


def _assess_reduction(ratio: float) -> tuple:
    """Determine the assessment based on the aggregate reduction ratio.

    Args:
        ratio: The aggregate reduction ratio (baseline / treatment).

    Returns:
        A tuple of (assessment, assessment_detail).
    """
    if ratio >= 10.0:
        return (
            "supported",
            f"Aggregate reduction ratio of {ratio:.2f}x falls within the claimed 10-15x range.",
        )
    elif ratio >= 5.0:
        return (
            "partially_supported",
            f"Aggregate reduction ratio of {ratio:.2f}x shows significant reduction "
            f"but falls below the claimed 10x minimum.",
        )
    else:
        return (
            "not_supported",
            f"Aggregate reduction ratio of {ratio:.2f}x does not support "
            f"the claimed 10-15x reduction.",
        )


def generate_comparison_report(
    baseline: RunRecord,
    treatment: RunRecord,
) -> ComparisonReport:
    """Compute per-session deltas, reduction ratios, and the 10–15x assessment.

    Sessions are matched by session_id between baseline and treatment.

    Args:
        baseline: The baseline RunRecord.
        treatment: The treatment RunRecord.

    Returns:
        A ComparisonReport with per-session comparisons and aggregate data.
    """
    # Build lookup by session_id
    baseline_map: Dict[int, object] = {
        s.session_id: s for s in baseline.sessions
    }
    treatment_map: Dict[int, object] = {
        s.session_id: s for s in treatment.sessions
    }

    # Find matched session IDs (preserve baseline order)
    matched_ids = [
        sid for sid in baseline_map if sid in treatment_map
    ]

    session_comparisons = []
    for sid in matched_ids:
        b_sess = baseline_map[sid]
        t_sess = treatment_map[sid]

        delta = TokenCount(
            input_tokens=t_sess.aggregate.input_tokens - b_sess.aggregate.input_tokens,
            output_tokens=t_sess.aggregate.output_tokens - b_sess.aggregate.output_tokens,
            total_tokens=t_sess.aggregate.total_tokens - b_sess.aggregate.total_tokens,
        )

        if t_sess.aggregate.total_tokens == 0:
            reduction_ratio = float("inf")
        else:
            reduction_ratio = b_sess.aggregate.total_tokens / t_sess.aggregate.total_tokens

        session_comparisons.append(
            SessionComparison(
                session_id=sid,
                task_type=b_sess.task_type,
                baseline=b_sess.aggregate,
                treatment=t_sess.aggregate,
                delta=delta,
                reduction_ratio=reduction_ratio,
            )
        )

    # Aggregate totals
    agg_baseline = TokenCount(
        input_tokens=sum(sc.baseline.input_tokens for sc in session_comparisons),
        output_tokens=sum(sc.baseline.output_tokens for sc in session_comparisons),
        total_tokens=sum(sc.baseline.total_tokens for sc in session_comparisons),
    )
    agg_treatment = TokenCount(
        input_tokens=sum(sc.treatment.input_tokens for sc in session_comparisons),
        output_tokens=sum(sc.treatment.output_tokens for sc in session_comparisons),
        total_tokens=sum(sc.treatment.total_tokens for sc in session_comparisons),
    )
    agg_delta = TokenCount(
        input_tokens=agg_treatment.input_tokens - agg_baseline.input_tokens,
        output_tokens=agg_treatment.output_tokens - agg_baseline.output_tokens,
        total_tokens=agg_treatment.total_tokens - agg_baseline.total_tokens,
    )

    if agg_treatment.total_tokens == 0:
        agg_ratio = float("inf")
    else:
        agg_ratio = agg_baseline.total_tokens / agg_treatment.total_tokens

    assessment, assessment_detail = _assess_reduction(agg_ratio)

    return ComparisonReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        sessions=session_comparisons,
        aggregate_baseline=agg_baseline,
        aggregate_treatment=agg_treatment,
        aggregate_delta=agg_delta,
        aggregate_reduction_ratio=agg_ratio,
        assessment=assessment,
        assessment_detail=assessment_detail,
    )


# ---------------------------------------------------------------------------
# 6.4  print_summary_table
# ---------------------------------------------------------------------------


def print_summary_table(report: ComparisonReport) -> None:
    """Print a rich Table summarising the comparison report.

    Columns: Session, Type, Baseline, Treatment, Delta, Ratio.
    One row per session, a final AGGREGATE row, and the assessment.

    Args:
        report: A ComparisonReport to display.
    """
    table = Table(title="Credit Usage Benchmark Comparison")

    table.add_column("Session", style="bold")
    table.add_column("Type")
    table.add_column("Baseline (mc)", justify="right")
    table.add_column("Treatment (mc)", justify="right")
    table.add_column("Delta (mc)", justify="right")
    table.add_column("Ratio", justify="right")

    for sc in report.sessions:
        ratio_str = _format_ratio(sc.reduction_ratio)
        table.add_row(
            str(sc.session_id),
            sc.task_type,
            str(sc.baseline.total_tokens),
            str(sc.treatment.total_tokens),
            str(sc.delta.total_tokens),
            ratio_str,
        )

    # Aggregate row
    agg_ratio_str = _format_ratio(report.aggregate_reduction_ratio)
    table.add_row(
        "[bold]AGGREGATE[/bold]",
        "",
        str(report.aggregate_baseline.total_tokens),
        str(report.aggregate_treatment.total_tokens),
        str(report.aggregate_delta.total_tokens),
        agg_ratio_str,
        style="bold",
    )

    console.print(table)
    console.print()
    console.print(f"Assessment: [bold]{report.assessment}[/bold]")
    if report.assessment_detail:
        console.print(report.assessment_detail)


def _format_ratio(ratio: float) -> str:
    """Format a reduction ratio with colour coding.

    Green if >= 10, yellow if >= 5, red if < 5.

    Args:
        ratio: The reduction ratio value.

    Returns:
        A rich-formatted string.
    """
    if ratio == float("inf"):
        return "[green]∞[/green]"
    elif ratio >= 10.0:
        return f"[green]{ratio:.2f}x[/green]"
    elif ratio >= 5.0:
        return f"[yellow]{ratio:.2f}x[/yellow]"
    else:
        return f"[red]{ratio:.2f}x[/red]"


# ---------------------------------------------------------------------------
# 6.5  write_comparison_report  /  write_token_report
# ---------------------------------------------------------------------------


def write_comparison_report(
    report: ComparisonReport,
    output_dir: str,
    format: str,
) -> None:
    """Write a ComparisonReport to disk in JSON or CSV format.

    Args:
        report: The ComparisonReport to write.
        output_dir: Directory to write the file into (created if needed).
        format: Either "json" or "csv".
    """
    os.makedirs(output_dir, exist_ok=True)

    if format == "json":
        path = os.path.join(output_dir, "comparison_report.json")
        with open(path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
    elif format == "csv":
        path = os.path.join(output_dir, "comparison_report.csv")
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "session_id",
                "task_type",
                "baseline_input",
                "baseline_output",
                "baseline_total",
                "treatment_input",
                "treatment_output",
                "treatment_total",
                "delta_input",
                "delta_output",
                "delta_total",
                "reduction_ratio",
            ])
            for sc in report.sessions:
                writer.writerow([
                    sc.session_id,
                    sc.task_type,
                    sc.baseline.input_tokens,
                    sc.baseline.output_tokens,
                    sc.baseline.total_tokens,
                    sc.treatment.input_tokens,
                    sc.treatment.output_tokens,
                    sc.treatment.total_tokens,
                    sc.delta.input_tokens,
                    sc.delta.output_tokens,
                    sc.delta.total_tokens,
                    sc.reduction_ratio,
                ])
            # AGGREGATE row
            writer.writerow([
                "AGGREGATE",
                "",
                report.aggregate_baseline.input_tokens,
                report.aggregate_baseline.output_tokens,
                report.aggregate_baseline.total_tokens,
                report.aggregate_treatment.input_tokens,
                report.aggregate_treatment.output_tokens,
                report.aggregate_treatment.total_tokens,
                report.aggregate_delta.input_tokens,
                report.aggregate_delta.output_tokens,
                report.aggregate_delta.total_tokens,
                report.aggregate_reduction_ratio,
            ])


def write_token_report(
    run: RunRecord,
    output_dir: str,
    format: str,
) -> None:
    """Write a Token_Report to disk in JSON or CSV format.

    File name is based on the run type: ``{run_type}_report.json`` or
    ``{run_type}_report.csv``.

    Args:
        run: The RunRecord to write.
        output_dir: Directory to write the file into (created if needed).
        format: Either "json" or "csv".
    """
    os.makedirs(output_dir, exist_ok=True)

    if format == "json":
        path = os.path.join(output_dir, f"{run.run_type}_report.json")
        with open(path, "w") as f:
            f.write(generate_token_report(run))
    elif format == "csv":
        path = os.path.join(output_dir, f"{run.run_type}_report.csv")
        with open(path, "w", newline="") as f:
            f.write(generate_token_report_csv(run))
