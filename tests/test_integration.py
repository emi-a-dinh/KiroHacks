"""Integration tests for the AI IDE Token Benchmark.

End-to-end tests that exercise the full pipeline:
  - ISSUES.md → session script generation → validation → round-trip
  - Mock run data → token reports → comparison report → correctness verification
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.models import (
    ComparisonReport,
    RunRecord,
    SessionRecord,
    TokenCount,
    TurnRecord,
)
from benchmark.reporter import (
    generate_comparison_report,
    generate_token_report,
    write_comparison_report,
    write_token_report,
)
from benchmark.session_script import (
    generate_session_script,
    parse_issues_md,
    parse_session_script,
    serialize_session_script,
    validate_session_script,
    write_session_script,
)


ISSUES_MD_PATH = str(Path(__file__).parent.parent / "example_project" / "ISSUES.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_turn(session_id: int, turn_number: int, inp: int, out: int, tools=None):
    return TurnRecord(
        session_id=session_id,
        turn_number=turn_number,
        tokens=TokenCount(inp, out, inp + out),
        mcp_tools_called=tools or [],
    )


def _make_session(session_id: int, task_type: str, turn_data):
    """Build a SessionRecord from a list of (input, output) tuples."""
    turns = [
        _make_turn(session_id, i + 1, inp, out)
        for i, (inp, out) in enumerate(turn_data)
    ]
    agg = TokenCount(
        input_tokens=sum(t.tokens.input_tokens for t in turns),
        output_tokens=sum(t.tokens.output_tokens for t in turns),
        total_tokens=sum(t.tokens.total_tokens for t in turns),
    )
    return SessionRecord(
        session_id=session_id,
        task_type=task_type,
        turns=turns,
        aggregate=agg,
    )


def _make_run(run_type: str, sessions):
    agg = TokenCount(
        input_tokens=sum(s.aggregate.input_tokens for s in sessions),
        output_tokens=sum(s.aggregate.output_tokens for s in sessions),
        total_tokens=sum(s.aggregate.total_tokens for s in sessions),
    )
    return RunRecord(
        run_type=run_type,
        timestamp="2024-06-01T12:00:00Z",
        prompt_file="benchmark_output/session_script.json",
        sessions=sessions,
        aggregate=agg,
    )


# ---------------------------------------------------------------------------
# 9.1  End-to-end session script generation
# ---------------------------------------------------------------------------


class TestFullSessionScriptGeneration:
    """End-to-end: ISSUES.md → session script with correct structure."""

    def test_full_session_script_generation(self):
        issues = parse_issues_md(ISSUES_MD_PATH)
        script = generate_session_script(issues, "example_project")

        # 10 sessions from 10 issues
        assert len(script.sessions) == 10

        # Each session has exactly 4 turns with correct roles
        for session in script.sessions:
            assert len(session.turns) == 4
            assert session.turns[0].role == "task_description"
            assert session.turns[1].role == "clarifying_question"
            assert session.turns[2].role == "implementation"
            assert session.turns[3].role == "verification"

        # Correct task_type labels based on ISSUES.md
        # Issue 1: single file (models/user.py)
        assert script.sessions[0].task_type == "single-file"
        # Issue 2: cross-file (models/task.py, routes/tasks.py)
        assert script.sessions[1].task_type == "cross-file"
        # Issue 4: cross-file (routes/tasks.py, utils/pagination.py)
        assert script.sessions[3].task_type == "cross-file"

        # Validate the script passes schema validation
        validate_session_script(script.to_dict())

        # Round-trip through JSON
        json_str = serialize_session_script(script)
        restored = parse_session_script(json_str)
        assert restored == script

    def test_full_session_script_write_and_reload(self):
        """End-to-end: generate → write to file → reload → verify identical."""
        issues = parse_issues_md(ISSUES_MD_PATH)
        script = generate_session_script(issues, "example_project")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session_script.json")
            write_session_script(script, path)

            with open(path) as f:
                restored = parse_session_script(f.read())

            assert restored == script

    def test_session_ids_match_issue_numbers(self):
        """Session IDs are sequential 1..10 matching the 10 issues."""
        issues = parse_issues_md(ISSUES_MD_PATH)
        script = generate_session_script(issues, "example_project")
        ids = [s.session_id for s in script.sessions]
        assert ids == list(range(1, 11))

    def test_task_description_contains_original_prompt(self):
        """Turn 1 of each session contains the original issue prompt."""
        issues = parse_issues_md(ISSUES_MD_PATH)
        script = generate_session_script(issues, "example_project")
        for session, issue in zip(script.sessions, issues):
            assert session.turns[0].prompt == issue["prompt"]

    def test_all_task_types_present(self):
        """The generated script contains both single-file and cross-file tasks."""
        issues = parse_issues_md(ISSUES_MD_PATH)
        script = generate_session_script(issues, "example_project")
        types = {s.task_type for s in script.sessions}
        assert "single-file" in types
        assert "cross-file" in types


# ---------------------------------------------------------------------------
# 9.2  Token_Report → Comparison_Report pipeline
# ---------------------------------------------------------------------------


class TestFullReportPipeline:
    """End-to-end: mock runs → token reports → comparison report → verify correctness."""

    def _build_baseline_and_treatment(self):
        """Build realistic mock data with multiple sessions.

        Baseline: high token counts (simulating full file reads).
        Treatment: low token counts (simulating Context Lens).
        Mix of single-file and cross-file sessions.
        """
        # Session 1: single-file bug fix — moderate reduction
        b1 = _make_session(1, "single-file", [
            (2000, 500),   # task_description
            (3000, 800),   # clarifying_question
            (4000, 1200),  # implementation
            (3500, 600),   # verification
        ])
        t1 = _make_session(1, "single-file", [
            (800, 300),
            (1000, 400),
            (1500, 500),
            (1200, 350),
        ])

        # Session 2: cross-file refactor — high reduction
        b2 = _make_session(2, "cross-file", [
            (5000, 1000),
            (8000, 1500),
            (10000, 2000),
            (7000, 1000),
        ])
        t2 = _make_session(2, "cross-file", [
            (400, 100),
            (600, 150),
            (800, 200),
            (500, 100),
        ])

        # Session 3: single-file security fix — moderate reduction
        b3 = _make_session(3, "single-file", [
            (1500, 400),
            (2500, 700),
            (3000, 900),
            (2000, 500),
        ])
        t3 = _make_session(3, "single-file", [
            (600, 200),
            (900, 300),
            (1100, 400),
            (800, 250),
        ])

        # Session 4: cross-file feature — high reduction
        b4 = _make_session(4, "cross-file", [
            (6000, 1200),
            (9000, 1800),
            (12000, 2500),
            (8000, 1500),
        ])
        t4 = _make_session(4, "cross-file", [
            (500, 120),
            (700, 180),
            (900, 250),
            (600, 150),
        ])

        baseline = _make_run("baseline", [b1, b2, b3, b4])
        treatment = _make_run("treatment", [t1, t2, t3, t4])
        return baseline, treatment

    def test_token_reports_are_valid_json(self):
        """Token reports serialize to valid JSON."""
        baseline, treatment = self._build_baseline_and_treatment()

        b_json = generate_token_report(baseline)
        t_json = generate_token_report(treatment)

        b_data = json.loads(b_json)
        t_data = json.loads(t_json)

        assert b_data["run_type"] == "baseline"
        assert t_data["run_type"] == "treatment"
        assert "sessions" in b_data
        assert "aggregate" in b_data

    def test_comparison_report_correct_deltas(self):
        """Comparison report has correct deltas: delta == treatment - baseline."""
        baseline, treatment = self._build_baseline_and_treatment()
        report = generate_comparison_report(baseline, treatment)

        for sc in report.sessions:
            b_sess = next(s for s in baseline.sessions if s.session_id == sc.session_id)
            t_sess = next(s for s in treatment.sessions if s.session_id == sc.session_id)

            assert sc.delta.input_tokens == t_sess.aggregate.input_tokens - b_sess.aggregate.input_tokens
            assert sc.delta.output_tokens == t_sess.aggregate.output_tokens - b_sess.aggregate.output_tokens
            assert sc.delta.total_tokens == t_sess.aggregate.total_tokens - b_sess.aggregate.total_tokens

    def test_comparison_report_correct_reduction_ratios(self):
        """Comparison report has correct reduction ratios: ratio == baseline / treatment."""
        baseline, treatment = self._build_baseline_and_treatment()
        report = generate_comparison_report(baseline, treatment)

        for sc in report.sessions:
            b_sess = next(s for s in baseline.sessions if s.session_id == sc.session_id)
            t_sess = next(s for s in treatment.sessions if s.session_id == sc.session_id)

            expected_ratio = b_sess.aggregate.total_tokens / t_sess.aggregate.total_tokens
            assert abs(sc.reduction_ratio - expected_ratio) < 1e-9

    def test_aggregation_correctness(self):
        """sum(turns) == session and sum(sessions) == run for all levels."""
        baseline, treatment = self._build_baseline_and_treatment()

        for run in [baseline, treatment]:
            # Turn-level → session-level
            for session in run.sessions:
                turn_input = sum(t.tokens.input_tokens for t in session.turns)
                turn_output = sum(t.tokens.output_tokens for t in session.turns)
                turn_total = sum(t.tokens.total_tokens for t in session.turns)
                assert session.aggregate.input_tokens == turn_input
                assert session.aggregate.output_tokens == turn_output
                assert session.aggregate.total_tokens == turn_total

            # Session-level → run-level
            sess_input = sum(s.aggregate.input_tokens for s in run.sessions)
            sess_output = sum(s.aggregate.output_tokens for s in run.sessions)
            sess_total = sum(s.aggregate.total_tokens for s in run.sessions)
            assert run.aggregate.input_tokens == sess_input
            assert run.aggregate.output_tokens == sess_output
            assert run.aggregate.total_tokens == sess_total

    def test_assessment_correctness(self):
        """Assessment is correct based on the aggregate reduction ratio."""
        baseline, treatment = self._build_baseline_and_treatment()
        report = generate_comparison_report(baseline, treatment)

        ratio = report.aggregate_reduction_ratio
        if ratio >= 10.0:
            assert report.assessment == "supported"
        elif ratio >= 5.0:
            assert report.assessment == "partially_supported"
        else:
            assert report.assessment == "not_supported"

    def test_aggregate_comparison_totals(self):
        """Aggregate baseline/treatment/delta in the comparison report are correct."""
        baseline, treatment = self._build_baseline_and_treatment()
        report = generate_comparison_report(baseline, treatment)

        # Aggregate baseline should equal sum of per-session baselines
        expected_b_total = sum(sc.baseline.total_tokens for sc in report.sessions)
        assert report.aggregate_baseline.total_tokens == expected_b_total

        # Aggregate treatment should equal sum of per-session treatments
        expected_t_total = sum(sc.treatment.total_tokens for sc in report.sessions)
        assert report.aggregate_treatment.total_tokens == expected_t_total

        # Aggregate delta should equal treatment - baseline
        assert report.aggregate_delta.total_tokens == expected_t_total - expected_b_total

        # Aggregate ratio should equal baseline / treatment
        expected_ratio = expected_b_total / expected_t_total
        assert abs(report.aggregate_reduction_ratio - expected_ratio) < 1e-9

    def test_write_and_reload_reports(self):
        """Generate → write to files → reload → verify identical."""
        baseline, treatment = self._build_baseline_and_treatment()
        report = generate_comparison_report(baseline, treatment)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write token reports
            write_token_report(baseline, tmpdir, "json")
            write_token_report(treatment, tmpdir, "json")

            # Reload and verify
            with open(os.path.join(tmpdir, "baseline_report.json")) as f:
                b_restored = RunRecord.from_dict(json.load(f))
            with open(os.path.join(tmpdir, "treatment_report.json")) as f:
                t_restored = RunRecord.from_dict(json.load(f))

            assert b_restored == baseline
            assert t_restored == treatment

            # Write comparison report
            write_comparison_report(report, tmpdir, "json")

            with open(os.path.join(tmpdir, "comparison_report.json")) as f:
                c_restored = ComparisonReport.from_dict(json.load(f))

            assert c_restored == report
