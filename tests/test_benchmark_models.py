"""Tests for benchmark data models and round-trip serialization."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.models import (
    Turn, Session, SessionScript, TokenCount, TurnRecord,
    SessionRecord, RunRecord, SessionComparison, ComparisonReport, BenchmarkConfig
)


class TestTurn:
    def test_create(self):
        t = Turn(1, "task_description", "Fix the bug")
        assert t.turn_number == 1
        assert t.role == "task_description"
        assert t.prompt == "Fix the bug"

    def test_round_trip(self):
        t = Turn(1, "task_description", "Fix the bug")
        assert Turn.from_dict(t.to_dict()) == t

    def test_to_dict_keys(self):
        t = Turn(1, "task_description", "Fix the bug")
        d = t.to_dict()
        assert set(d.keys()) == {"turn_number", "role", "prompt"}


class TestSession:
    def test_create(self):
        t = Turn(1, "task_description", "Fix the bug")
        s = Session(1, 1, "Fix bug", "single-file", ["app.py"], [t])
        assert s.session_id == 1
        assert s.task_type == "single-file"
        assert s.files == ["app.py"]
        assert len(s.turns) == 1

    def test_round_trip(self):
        t = Turn(1, "task_description", "Fix the bug")
        s = Session(1, 1, "Fix bug", "single-file", ["app.py"], [t])
        assert Session.from_dict(s.to_dict()) == s

    def test_cross_file(self):
        t = Turn(1, "task_description", "Refactor")
        s = Session(2, 2, "Refactor", "cross-file", ["a.py", "b.py"], [t])
        assert s.task_type == "cross-file"
        assert len(s.files) == 2


class TestSessionScript:
    def test_round_trip(self):
        t = Turn(1, "task_description", "Fix the bug")
        s = Session(1, 1, "Fix bug", "single-file", ["app.py"], [t])
        ss = SessionScript("2024-01-01", "/repo", [s])
        assert SessionScript.from_dict(ss.to_dict()) == ss


class TestTokenCount:
    def test_create(self):
        tc = TokenCount(100, 50, 150)
        assert tc.input_tokens == 100
        assert tc.output_tokens == 50
        assert tc.total_tokens == 150

    def test_round_trip(self):
        tc = TokenCount(100, 50, 150)
        assert TokenCount.from_dict(tc.to_dict()) == tc


class TestTurnRecord:
    def test_round_trip(self):
        tc = TokenCount(100, 50, 150)
        tr = TurnRecord(1, 1, tc, ["context_query"])
        assert TurnRecord.from_dict(tr.to_dict()) == tr

    def test_default_mcp_tools(self):
        tc = TokenCount(100, 50, 150)
        tr = TurnRecord(1, 1, tc)
        assert tr.mcp_tools_called == []
        assert TurnRecord.from_dict(tr.to_dict()) == tr


class TestSessionRecord:
    def test_round_trip(self):
        tc = TokenCount(100, 50, 150)
        tr = TurnRecord(1, 1, tc)
        sr = SessionRecord(1, "single-file", [tr], tc)
        assert SessionRecord.from_dict(sr.to_dict()) == sr


class TestRunRecord:
    def test_round_trip(self):
        tc = TokenCount(100, 50, 150)
        tr = TurnRecord(1, 1, tc)
        sr = SessionRecord(1, "single-file", [tr], tc)
        rr = RunRecord("baseline", "2024-01-01", "script.json", [sr], tc)
        assert RunRecord.from_dict(rr.to_dict()) == rr


class TestSessionComparison:
    def test_round_trip(self):
        tc = TokenCount(100, 50, 150)
        zero = TokenCount(0, 0, 0)
        sc = SessionComparison(1, "single-file", tc, tc, zero, 1.0)
        assert SessionComparison.from_dict(sc.to_dict()) == sc


class TestComparisonReport:
    def test_round_trip(self):
        tc = TokenCount(100, 50, 150)
        zero = TokenCount(0, 0, 0)
        sc = SessionComparison(1, "single-file", tc, tc, zero, 1.0)
        cr = ComparisonReport("2024-01-01", [sc], tc, tc, zero, 1.0, "supported", "detail")
        assert ComparisonReport.from_dict(cr.to_dict()) == cr

    def test_default_assessment_detail(self):
        tc = TokenCount(100, 50, 150)
        zero = TokenCount(0, 0, 0)
        sc = SessionComparison(1, "single-file", tc, tc, zero, 1.0)
        cr = ComparisonReport("2024-01-01", [sc], tc, tc, zero, 1.0, "supported")
        assert cr.assessment_detail == ""
        assert ComparisonReport.from_dict(cr.to_dict()) == cr


class TestBenchmarkConfig:
    def test_defaults(self):
        bc = BenchmarkConfig("example_project")
        assert bc.prompt_file == "benchmark_output/session_script.json"
        assert bc.output_dir == "benchmark_output"
        assert bc.output_format == "json"
        assert bc.proxy_port == 8080
        assert bc.timeout_seconds == 120

    def test_round_trip(self):
        bc = BenchmarkConfig("example_project")
        assert BenchmarkConfig.from_dict(bc.to_dict()) == bc

    def test_custom_values_round_trip(self):
        bc = BenchmarkConfig("repo", "custom.json", "out", "csv", 9090, 60)
        assert BenchmarkConfig.from_dict(bc.to_dict()) == bc

    def test_from_dict_applies_defaults(self):
        bc = BenchmarkConfig.from_dict({"repo_path": "my_repo"})
        assert bc.repo_path == "my_repo"
        assert bc.prompt_file == "benchmark_output/session_script.json"
        assert bc.output_dir == "benchmark_output"
        assert bc.output_format == "json"
        assert bc.proxy_port == 8080
        assert bc.timeout_seconds == 120
