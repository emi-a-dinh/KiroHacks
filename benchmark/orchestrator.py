"""Run orchestrator for the AI IDE Token Benchmark.

Drives the benchmark flow: baseline run → treatment run. Uses the
AutomationDriver to launch Kiro, deliver prompts, and detect responses
automatically. Uses the PowerManager to toggle the token-miser Power
between baseline (disabled) and treatment (enabled) runs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Tuple

from rich.console import Console

from benchmark.automation_driver import AutomationDriver, PowerManager
from benchmark.models import (
    BenchmarkConfig,
    BenchmarkError,
    RunRecord,
    SessionRecord,
    SessionScript,
    TokenCount,
    TurnRecord,
)
from benchmark.proxy import ProxyManager
from benchmark.reporter import write_token_report


console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 5.6  Module-level aggregate helpers
# ---------------------------------------------------------------------------


def compute_session_aggregate(turns: List[TurnRecord]) -> TokenCount:
    """Compute the aggregate TokenCount for a session from its turns.

    Args:
        turns: List of TurnRecord instances for the session.

    Returns:
        A TokenCount with summed input, output, and total tokens.
    """
    return TokenCount(
        input_tokens=sum(t.tokens.input_tokens for t in turns),
        output_tokens=sum(t.tokens.output_tokens for t in turns),
        total_tokens=sum(t.tokens.total_tokens for t in turns),
    )


def compute_run_aggregate(sessions: List[SessionRecord]) -> TokenCount:
    """Compute the aggregate TokenCount for a run from its sessions.

    Args:
        sessions: List of SessionRecord instances for the run.

    Returns:
        A TokenCount with summed input, output, and total tokens.
    """
    return TokenCount(
        input_tokens=sum(s.aggregate.input_tokens for s in sessions),
        output_tokens=sum(s.aggregate.output_tokens for s in sessions),
        total_tokens=sum(s.aggregate.total_tokens for s in sessions),
    )


# ---------------------------------------------------------------------------
# 5.1  Orchestrator class
# ---------------------------------------------------------------------------


class Orchestrator:
    """Drives the benchmark flow through baseline and treatment runs.

    Uses AutomationDriver for prompt delivery and response detection,
    and PowerManager for toggling the token-miser Power between runs.

    Args:
        script: The session script containing all sessions and turns.
        proxy: The proxy manager for reading captured token data.
        config: The benchmark configuration.
    """

    def __init__(
        self,
        script: SessionScript,
        proxy: ProxyManager,
        config: BenchmarkConfig,
    ) -> None:
        self.script = script
        self.proxy = proxy
        self.config = config
        self._automation_driver = AutomationDriver(proxy, config)
        self._power_manager = PowerManager(config.repo_path)

    # -------------------------------------------------------------------
    # 5.2 / 5.5  run_single
    # -------------------------------------------------------------------

    def run_single(self, run_type: str) -> RunRecord:
        """Execute all sessions/turns for one run condition automatically.

        For each session, sends each turn's prompt via the AutomationDriver,
        which delivers it to Kiro's stdin and waits for the response by
        monitoring the proxy JSONL file. Builds TurnRecords from the
        captured token data.

        Args:
            run_type: Either "baseline" or "treatment".

        Returns:
            A RunRecord containing all session records and the run aggregate.
        """
        session_records: List[SessionRecord] = []

        for sess_idx, session in enumerate(self.script.sessions):
            # Print session header
            console.print()
            console.print(
                f"[bold cyan]━━━ Session {session.session_id}: "
                f"{session.title} ({session.task_type}) ━━━[/bold cyan]"
            )
            console.print()

            turn_records: List[TurnRecord] = []

            for turn in session.turns:
                # Send prompt via AutomationDriver and wait for response
                entries, timed_out = self._automation_driver.run_turn(
                    turn.prompt,
                    run_type,
                    turn.role,
                    session.session_id,
                    turn.turn_number,
                )

                if timed_out:
                    console.print(
                        f"[yellow]⚠ Turn {turn.turn_number} timed out "
                        f"(session {session.session_id})[/yellow]"
                    )

                # Process entries into a TurnRecord
                turn_record = self._build_turn_record(
                    session.session_id, turn.turn_number, entries
                )
                turn_records.append(turn_record)

                # Progress line after each turn
                console.print(
                    f"  [{run_type}] Session {session.session_id}, "
                    f"Turn {turn.turn_number}: "
                    f"{turn_record.tokens.total_tokens} tokens"
                )

            # Compute session aggregate
            session_aggregate = compute_session_aggregate(turn_records)
            session_record = SessionRecord(
                session_id=session.session_id,
                task_type=session.task_type,
                turns=turn_records,
                aggregate=session_aggregate,
            )
            session_records.append(session_record)

            # Session summary line
            console.print(
                f"  Session {session.session_id} total: "
                f"{session_aggregate.total_tokens} tokens"
            )

            # Start new conversation between sessions (not after the last one)
            if sess_idx < len(self.script.sessions) - 1:
                self._automation_driver.new_conversation()

        # Compute run aggregate
        run_aggregate = compute_run_aggregate(session_records)

        # Run total line
        console.print()
        console.print(
            f"[bold]{run_type.capitalize()} run total: "
            f"{run_aggregate.total_tokens} tokens[/bold]"
        )

        return RunRecord(
            run_type=run_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            prompt_file=self.config.prompt_file,
            sessions=session_records,
            aggregate=run_aggregate,
        )

    # -------------------------------------------------------------------
    # 5.4  run_benchmark
    # -------------------------------------------------------------------

    def run_benchmark(self) -> Tuple[RunRecord, RunRecord]:
        """Orchestrate baseline then treatment runs automatically.

        Manages the full lifecycle:
        1. Backs up Power state
        2. Disables Power, runs baseline
        3. Enables Power, runs treatment
        4. Restores Power state (guaranteed via finally)

        Returns:
            A tuple of (baseline_record, treatment_record).

        Raises:
            BenchmarkError: If the benchmark cannot complete due to
                unrecoverable errors (Kiro failures, max restarts, etc.).
        """
        self._power_manager.backup()

        # Log resolved automation config
        auto_cfg = self.config.automation
        logger.info(
            "Automation config: kiro_path=%s, idle_timeout=%d, "
            "turn_timeout=%d, startup_timeout=%d",
            auto_cfg.kiro_path,
            auto_cfg.idle_timeout,
            auto_cfg.turn_timeout,
            auto_cfg.startup_timeout,
        )

        baseline = None
        treatment = None
        try:
            # --- Baseline run ---
            console.print()
            console.print("[bold]BASELINE RUN[/bold] (Power disabled)")
            self._power_manager.disable_power()
            self._automation_driver.start_kiro()
            self._automation_driver.reset_restart_count()
            baseline = self.run_single("baseline")
            self._automation_driver.stop_kiro()

            # --- Treatment run ---
            console.print()
            console.print("[bold]TREATMENT RUN[/bold] (Power enabled)")
            self._power_manager.enable_power()
            self._automation_driver.start_kiro()
            self._automation_driver.reset_restart_count()
            treatment = self.run_single("treatment")
            self._automation_driver.stop_kiro()

            return baseline, treatment

        except BenchmarkError:
            # Write partial reports if available
            if baseline is not None:
                try:
                    write_token_report(
                        baseline,
                        self.config.output_dir,
                        self.config.output_format,
                    )
                    console.print(
                        "[yellow]Partial baseline report written.[/yellow]"
                    )
                except Exception:
                    logger.exception("Failed to write partial baseline report")
            if treatment is not None:
                try:
                    write_token_report(
                        treatment,
                        self.config.output_dir,
                        self.config.output_format,
                    )
                    console.print(
                        "[yellow]Partial treatment report written.[/yellow]"
                    )
                except Exception:
                    logger.exception("Failed to write partial treatment report")
            raise

        finally:
            self._automation_driver.stop_kiro()
            self._power_manager.restore()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _build_turn_record(
        self,
        session_id: int,
        turn_number: int,
        entries: List[dict],
    ) -> TurnRecord:
        """Build a TurnRecord from JSONL entries captured by the proxy.

        Filters entries by type:
        - "token_usage": sums input_tokens and output_tokens
        - "mcp_tool_call": collects tool names

        Args:
            session_id: The current session ID.
            turn_number: The current turn number.
            entries: List of parsed JSONL dicts from the proxy.

        Returns:
            A TurnRecord with aggregated token data and MCP tool list.
        """
        total_input = 0
        total_output = 0
        mcp_tools: List[str] = []
        found_token_usage = False

        for entry in entries:
            entry_type = entry.get("type", "")

            if entry_type == "token_usage":
                found_token_usage = True
                total_input += entry.get("input_tokens", 0)
                total_output += entry.get("output_tokens", 0)

            elif entry_type == "mcp_tool_call":
                tools = entry.get("tools", [])
                for tool in tools:
                    if tool not in mcp_tools:
                        mcp_tools.append(tool)

        if not found_token_usage:
            console.print(
                f"[yellow]⚠ No token_usage entries found for "
                f"session {session_id}, turn {turn_number}. "
                f"Using zero token counts.[/yellow]"
            )

        tokens = TokenCount(
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
        )

        return TurnRecord(
            session_id=session_id,
            turn_number=turn_number,
            tokens=tokens,
            mcp_tools_called=mcp_tools,
        )
