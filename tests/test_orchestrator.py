"""Tests for the orchestrator module.

Tests the pure computation functions (compute_session_aggregate,
compute_run_aggregate), the Orchestrator.__init__ constructor, and
the _build_turn_record helper.
"""

from benchmark.automation_driver import AutomationDriver, PowerManager
from benchmark.models import (
    BenchmarkConfig,
    SessionRecord,
    SessionScript,
    TokenCount,
    TurnRecord,
)
from benchmark.orchestrator import (
    Orchestrator,
    compute_run_aggregate,
    compute_session_aggregate,
)
from benchmark.proxy import ProxyManager


# ---------------------------------------------------------------------------
# compute_session_aggregate
# ---------------------------------------------------------------------------


class TestComputeSessionAggregate:
    def test_single_turn(self):
        turns = [
            TurnRecord(
                session_id=1,
                turn_number=1,
                tokens=TokenCount(input_tokens=100, output_tokens=50, total_tokens=150),
            ),
        ]
        result = compute_session_aggregate(turns)
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150

    def test_multiple_turns(self):
        turns = [
            TurnRecord(
                session_id=1,
                turn_number=1,
                tokens=TokenCount(input_tokens=100, output_tokens=50, total_tokens=150),
            ),
            TurnRecord(
                session_id=1,
                turn_number=2,
                tokens=TokenCount(input_tokens=200, output_tokens=80, total_tokens=280),
            ),
            TurnRecord(
                session_id=1,
                turn_number=3,
                tokens=TokenCount(input_tokens=300, output_tokens=120, total_tokens=420),
            ),
        ]
        result = compute_session_aggregate(turns)
        assert result.input_tokens == 600
        assert result.output_tokens == 250
        assert result.total_tokens == 850

    def test_empty_turns(self):
        result = compute_session_aggregate([])
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0

    def test_zero_token_turns(self):
        turns = [
            TurnRecord(
                session_id=1,
                turn_number=1,
                tokens=TokenCount(input_tokens=0, output_tokens=0, total_tokens=0),
            ),
            TurnRecord(
                session_id=1,
                turn_number=2,
                tokens=TokenCount(input_tokens=0, output_tokens=0, total_tokens=0),
            ),
        ]
        result = compute_session_aggregate(turns)
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


# ---------------------------------------------------------------------------
# compute_run_aggregate
# ---------------------------------------------------------------------------


class TestComputeRunAggregate:
    def test_single_session(self):
        sessions = [
            SessionRecord(
                session_id=1,
                task_type="single-file",
                turns=[],
                aggregate=TokenCount(input_tokens=500, output_tokens=200, total_tokens=700),
            ),
        ]
        result = compute_run_aggregate(sessions)
        assert result.input_tokens == 500
        assert result.output_tokens == 200
        assert result.total_tokens == 700

    def test_multiple_sessions(self):
        sessions = [
            SessionRecord(
                session_id=1,
                task_type="single-file",
                turns=[],
                aggregate=TokenCount(input_tokens=500, output_tokens=200, total_tokens=700),
            ),
            SessionRecord(
                session_id=2,
                task_type="cross-file",
                turns=[],
                aggregate=TokenCount(input_tokens=1000, output_tokens=400, total_tokens=1400),
            ),
            SessionRecord(
                session_id=3,
                task_type="single-file",
                turns=[],
                aggregate=TokenCount(input_tokens=300, output_tokens=100, total_tokens=400),
            ),
        ]
        result = compute_run_aggregate(sessions)
        assert result.input_tokens == 1800
        assert result.output_tokens == 700
        assert result.total_tokens == 2500

    def test_empty_sessions(self):
        result = compute_run_aggregate([])
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


# ---------------------------------------------------------------------------
# Orchestrator.__init__
# ---------------------------------------------------------------------------


class TestOrchestratorInit:
    def test_stores_references(self):
        script = SessionScript(
            generated_at="2025-01-01T00:00:00Z",
            repo_path="example_project",
            sessions=[],
        )
        proxy = ProxyManager(port=8080, jsonl_path="/tmp/test.jsonl")
        config = BenchmarkConfig(repo_path="example_project")

        orch = Orchestrator(script=script, proxy=proxy, config=config)

        assert orch.script is script
        assert orch.proxy is proxy
        assert orch.config is config

    def test_creates_automation_driver(self):
        script = SessionScript(
            generated_at="2025-01-01T00:00:00Z",
            repo_path="example_project",
            sessions=[],
        )
        proxy = ProxyManager(port=8080, jsonl_path="/tmp/test.jsonl")
        config = BenchmarkConfig(repo_path="example_project")

        orch = Orchestrator(script=script, proxy=proxy, config=config)

        assert isinstance(orch._automation_driver, AutomationDriver)

    def test_creates_power_manager(self):
        script = SessionScript(
            generated_at="2025-01-01T00:00:00Z",
            repo_path="example_project",
            sessions=[],
        )
        proxy = ProxyManager(port=9090, jsonl_path="/tmp/other.jsonl")
        config = BenchmarkConfig(repo_path="example_project", proxy_port=9090)

        orch = Orchestrator(script=script, proxy=proxy, config=config)

        assert isinstance(orch._power_manager, PowerManager)
