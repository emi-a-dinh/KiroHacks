"""Tests for benchmark/reporter.py — Token_Report and Comparison_Report generation."""

import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.models import (
    ComparisonReport,
    RunRecord,
    SessionComparison,
    SessionRecord,
    TokenCount,
    TurnRecord,
)
from benchmark.reporter import (
    generate_comparison_report,
    generate_token_report,
    generate_token_report_csv,
    write_comparison_report,
    write_token_report,
)


# ---------------------------------------------------------------------------
# Helpers to build test data
# ---------------------------------------------------------------------------


def _make_turn_record(session_id: int, turn_number: int, inp: int, out: int, tools=None):
    return TurnRecord(
        session_id=session_id,
        turn_number=turn_number,
        tokens=TokenCount(inp, out, inp + out),
        mcp_tools_called=tools or [],
    )


def _make_session_record(session_id: int, task_type: str, turns_data):
    """turns_data: list of (input, output) tuples."""
    turns = [
        _make_turn_record(session_id, i + 1, inp, out)
        for i, (inp, out) in enumerate(turns_data)
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


def _make_run_record(run_type: str, sessions):
    agg = TokenCount(
        input_tokens=sum(s.aggregate.input_tokens for s in sessions),
        output_tokens=sum(s.aggregate.output_tokens for s in sessions),
        total_tokens=sum(s.aggregate.total_tokens for s in sessions),
    )
    return RunRecord(
        run_type=run_type,
        timestamp="2024-01-01T00:00:00Z",
        prompt_file="script.json",
        sessions=sessions,
        aggregate=agg,
    )


# ---------------------------------------------------------------------------
# 6.1  generate_token_report
# ---------------------------------------------------------------------------


class TestGenerateTokenReport:
    def test_produces_valid_json(self):
        s = _make_session_record(1, "single-file", [(100, 50), (200, 80)])
        run = _make_run_record("baseline", [s])
        result = generate_token_report(run)
        data = json.loads(result)
        assert data["run_type"] == "baseline"
        assert data["timestamp"] == "2024-01-01T00:00:00Z"
        assert data["prompt_file"] == "script.json"

    def test_correct_structure(self):
        s = _make_session_record(1, "single-file", [(100, 50)])
        run = _make_run_record("treatment", [s])
        data = json.loads(generate_token_report(run))
        assert "sessions" in data
        assert "aggregate" in data
        session = data["sessions"][0]
        assert "turns" in session
        assert "aggregate" in session
        turn = session["turns"][0]
        assert "tokens" in turn
        assert turn["tokens"]["input_tokens"] == 100
        assert turn["tokens"]["output_tokens"] == 50
        assert turn["tokens"]["total_tokens"] == 150

    def test_aggregate_values(self):
        s1 = _make_session_record(1, "single-file", [(100, 50), (200, 80)])
        s2 = _make_session_record(2, "cross-file", [(300, 100)])
        run = _make_run_record("baseline", [s1, s2])
        data = json.loads(generate_token_report(run))
        assert data["aggregate"]["input_tokens"] == 600
        assert data["aggregate"]["output_tokens"] == 230
        assert data["aggregate"]["total_tokens"] == 830


# ---------------------------------------------------------------------------
# 6.2  generate_token_report_csv
# ---------------------------------------------------------------------------


class TestGenerateTokenReportCsv:
    def test_produces_valid_csv(self):
        s = _make_session_record(1, "single-file", [(100, 50), (200, 80)])
        run = _make_run_record("baseline", [s])
        result = generate_token_report_csv(run)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        # header + 2 turns + 1 session TOTAL + 1 AGGREGATE = 5 rows
        assert len(rows) == 5

    def test_correct_columns(self):
        s = _make_session_record(1, "single-file", [(100, 50)])
        run = _make_run_record("baseline", [s])
        result = generate_token_report_csv(run)
        reader = csv.reader(io.StringIO(result))
        header = next(reader)
        assert header == [
            "session_id", "task_type", "turn_number",
            "input_tokens", "output_tokens", "total_tokens",
            "mcp_tools_called",
        ]

    def test_session_total_row(self):
        s = _make_session_record(1, "single-file", [(100, 50), (200, 80)])
        run = _make_run_record("baseline", [s])
        result = generate_token_report_csv(run)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        # Row index 3 is the session TOTAL (header=0, turn1=1, turn2=2, TOTAL=3)
        total_row = rows[3]
        assert total_row[2] == "TOTAL"
        assert total_row[3] == "300"   # 100 + 200
        assert total_row[4] == "130"   # 50 + 80
        assert total_row[5] == "430"   # 150 + 280

    def test_aggregate_row(self):
        s = _make_session_record(1, "single-file", [(100, 50)])
        run = _make_run_record("baseline", [s])
        result = generate_token_report_csv(run)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        last_row = rows[-1]
        assert last_row[0] == "AGGREGATE"
        assert last_row[3] == "100"
        assert last_row[4] == "50"
        assert last_row[5] == "150"


# ---------------------------------------------------------------------------
# 6.3  generate_comparison_report
# ---------------------------------------------------------------------------


class TestGenerateComparisonReport:
    def test_correct_deltas(self):
        b_sess = _make_session_record(1, "single-file", [(1000, 500)])
        t_sess = _make_session_record(1, "single-file", [(100, 50)])
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])

        report = generate_comparison_report(baseline, treatment)
        sc = report.sessions[0]
        assert sc.delta.input_tokens == 100 - 1000
        assert sc.delta.output_tokens == 50 - 500
        assert sc.delta.total_tokens == 150 - 1500

    def test_correct_reduction_ratio(self):
        b_sess = _make_session_record(1, "single-file", [(1000, 500)])
        t_sess = _make_session_record(1, "single-file", [(100, 50)])
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])

        report = generate_comparison_report(baseline, treatment)
        sc = report.sessions[0]
        assert sc.reduction_ratio == 1500 / 150  # 10.0

    def test_assessment_supported(self):
        b_sess = _make_session_record(1, "single-file", [(10000, 5000)])
        t_sess = _make_session_record(1, "single-file", [(100, 50)])
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])

        report = generate_comparison_report(baseline, treatment)
        assert report.assessment == "supported"

    def test_assessment_partially_supported(self):
        b_sess = _make_session_record(1, "single-file", [(500, 250)])
        t_sess = _make_session_record(1, "single-file", [(100, 50)])
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])

        report = generate_comparison_report(baseline, treatment)
        # ratio = 750 / 150 = 5.0 → partially_supported
        assert report.assessment == "partially_supported"

    def test_assessment_not_supported(self):
        b_sess = _make_session_record(1, "single-file", [(200, 100)])
        t_sess = _make_session_record(1, "single-file", [(100, 50)])
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])

        report = generate_comparison_report(baseline, treatment)
        # ratio = 300 / 150 = 2.0 → not_supported
        assert report.assessment == "not_supported"

    def test_aggregate_totals(self):
        b1 = _make_session_record(1, "single-file", [(1000, 500)])
        b2 = _make_session_record(2, "cross-file", [(2000, 800)])
        t1 = _make_session_record(1, "single-file", [(100, 50)])
        t2 = _make_session_record(2, "cross-file", [(200, 80)])
        baseline = _make_run_record("baseline", [b1, b2])
        treatment = _make_run_record("treatment", [t1, t2])

        report = generate_comparison_report(baseline, treatment)
        assert report.aggregate_baseline.total_tokens == 1500 + 2800
        assert report.aggregate_treatment.total_tokens == 150 + 280
        assert report.aggregate_delta.total_tokens == (150 + 280) - (1500 + 2800)

    def test_division_by_zero_treatment_zero(self):
        """When treatment total is 0, reduction_ratio should be inf."""
        b_sess = _make_session_record(1, "single-file", [(1000, 500)])
        # Treatment with zero tokens
        t_sess = SessionRecord(
            session_id=1,
            task_type="single-file",
            turns=[],
            aggregate=TokenCount(0, 0, 0),
        )
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])

        report = generate_comparison_report(baseline, treatment)
        sc = report.sessions[0]
        assert sc.reduction_ratio == float("inf")
        assert report.aggregate_reduction_ratio == float("inf")

    def test_multiple_sessions_matched_by_id(self):
        """Sessions are matched by session_id, not by position."""
        b1 = _make_session_record(1, "single-file", [(100, 50)])
        b2 = _make_session_record(3, "cross-file", [(300, 100)])
        t1 = _make_session_record(3, "cross-file", [(30, 10)])
        t2 = _make_session_record(1, "single-file", [(10, 5)])
        baseline = _make_run_record("baseline", [b1, b2])
        treatment = _make_run_record("treatment", [t1, t2])

        report = generate_comparison_report(baseline, treatment)
        assert len(report.sessions) == 2
        # Verify session 1 matched correctly
        s1 = next(sc for sc in report.sessions if sc.session_id == 1)
        assert s1.baseline.total_tokens == 150
        assert s1.treatment.total_tokens == 15


# ---------------------------------------------------------------------------
# 6.5  write_comparison_report / write_token_report
# ---------------------------------------------------------------------------


class TestWriteComparisonReport:
    def _make_report(self):
        b_sess = _make_session_record(1, "single-file", [(1000, 500)])
        t_sess = _make_session_record(1, "single-file", [(100, 50)])
        baseline = _make_run_record("baseline", [b_sess])
        treatment = _make_run_record("treatment", [t_sess])
        return generate_comparison_report(baseline, treatment)

    def test_json_output(self):
        report = self._make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            write_comparison_report(report, tmpdir, "json")
            path = os.path.join(tmpdir, "comparison_report.json")
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert "sessions" in data
            assert "assessment" in data

    def test_csv_output(self):
        report = self._make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            write_comparison_report(report, tmpdir, "csv")
            path = os.path.join(tmpdir, "comparison_report.csv")
            assert os.path.exists(path)
            with open(path) as f:
                reader = csv.reader(f)
                rows = list(reader)
            # header + 1 session + AGGREGATE = 3 rows
            assert len(rows) == 3
            assert rows[0][0] == "session_id"
            assert rows[-1][0] == "AGGREGATE"

    def test_creates_output_dir(self):
        report = self._make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "nested", "dir")
            write_comparison_report(report, nested, "json")
            assert os.path.exists(os.path.join(nested, "comparison_report.json"))


class TestWriteTokenReport:
    def test_json_output(self):
        s = _make_session_record(1, "single-file", [(100, 50)])
        run = _make_run_record("baseline", [s])
        with tempfile.TemporaryDirectory() as tmpdir:
            write_token_report(run, tmpdir, "json")
            path = os.path.join(tmpdir, "baseline_report.json")
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["run_type"] == "baseline"

    def test_csv_output(self):
        s = _make_session_record(1, "single-file", [(100, 50)])
        run = _make_run_record("treatment", [s])
        with tempfile.TemporaryDirectory() as tmpdir:
            write_token_report(run, tmpdir, "csv")
            path = os.path.join(tmpdir, "treatment_report.csv")
            assert os.path.exists(path)
            with open(path) as f:
                reader = csv.reader(f)
                header = next(reader)
            assert "session_id" in header

    def test_creates_output_dir(self):
        s = _make_session_record(1, "single-file", [(100, 50)])
        run = _make_run_record("baseline", [s])
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "deep", "path")
            write_token_report(run, nested, "json")
            assert os.path.exists(os.path.join(nested, "baseline_report.json"))


# ---------------------------------------------------------------------------
# 8.3  Property-based test: token aggregation correctness
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings
from benchmark.orchestrator import compute_session_aggregate, compute_run_aggregate


token_count_strategy = st.builds(
    TokenCount,
    input_tokens=st.integers(min_value=0, max_value=100000),
    output_tokens=st.integers(min_value=0, max_value=100000),
    total_tokens=st.just(0),  # placeholder, will be computed
).map(lambda tc: TokenCount(tc.input_tokens, tc.output_tokens, tc.input_tokens + tc.output_tokens))

turn_record_strategy = st.builds(
    TurnRecord,
    session_id=st.just(1),
    turn_number=st.integers(min_value=1, max_value=10),
    tokens=token_count_strategy,
    mcp_tools_called=st.just([]),
)


class TestAggregationCorrectnessProperty:
    """**Validates: Requirements 4.5, 4.6**"""

    @given(turns=st.lists(turn_record_strategy, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_aggregation_correctness_property(self, turns):
        """sum(turn tokens) == session aggregate for arbitrary turns."""
        agg = compute_session_aggregate(turns)
        assert agg.input_tokens == sum(t.tokens.input_tokens for t in turns)
        assert agg.output_tokens == sum(t.tokens.output_tokens for t in turns)
        assert agg.total_tokens == sum(t.tokens.total_tokens for t in turns)


# ---------------------------------------------------------------------------
# 8.4  Property-based test: comparison delta correctness
# ---------------------------------------------------------------------------


class TestComparisonDeltaCorrectnessProperty:
    """**Validates: Requirements 6.7**"""

    @given(
        baseline_total=st.integers(min_value=0, max_value=100000),
        treatment_total=st.integers(min_value=0, max_value=100000),
    )
    @settings(max_examples=50)
    def test_comparison_delta_correctness_property(self, baseline_total, treatment_total):
        """delta == treatment - baseline for each metric."""
        b_sess = SessionRecord(1, "single-file", [], TokenCount(baseline_total, 0, baseline_total))
        t_sess = SessionRecord(1, "single-file", [], TokenCount(treatment_total, 0, treatment_total))
        baseline = RunRecord("baseline", "t", "f", [b_sess], TokenCount(baseline_total, 0, baseline_total))
        treatment = RunRecord("treatment", "t", "f", [t_sess], TokenCount(treatment_total, 0, treatment_total))

        report = generate_comparison_report(baseline, treatment)
        sc = report.sessions[0]
        assert sc.delta.total_tokens == treatment_total - baseline_total
        assert sc.delta.input_tokens == treatment_total - baseline_total


# ---------------------------------------------------------------------------
# 8.5  Property-based test: reduction ratio correctness
# ---------------------------------------------------------------------------


class TestReductionRatioCorrectnessProperty:
    """**Validates: Requirements 6.8**"""

    @given(
        baseline_total=st.integers(min_value=1, max_value=100000),
        treatment_total=st.integers(min_value=1, max_value=100000),
    )
    @settings(max_examples=50)
    def test_reduction_ratio_correctness_property(self, baseline_total, treatment_total):
        """ratio == baseline / treatment for each metric (where treatment > 0)."""
        b_sess = SessionRecord(1, "single-file", [], TokenCount(baseline_total, 0, baseline_total))
        t_sess = SessionRecord(1, "single-file", [], TokenCount(treatment_total, 0, treatment_total))
        baseline = RunRecord("baseline", "t", "f", [b_sess], TokenCount(baseline_total, 0, baseline_total))
        treatment = RunRecord("treatment", "t", "f", [t_sess], TokenCount(treatment_total, 0, treatment_total))

        report = generate_comparison_report(baseline, treatment)
        sc = report.sessions[0]
        expected_ratio = baseline_total / treatment_total
        assert abs(sc.reduction_ratio - expected_ratio) < 1e-9
