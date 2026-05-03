"""Run orchestrator for the AI IDE Token Benchmark.

Drives the benchmark flow: baseline run → treatment run. Displays current
session/turn to the user via rich terminal UI, waits for user input, and
reads token data from the proxy's JSONL output after each turn.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel

from benchmark.models import (
    BenchmarkConfig,
    RunRecord,
    SessionRecord,
    SessionScript,
    TokenCount,
    TurnRecord,
)
from benchmark.proxy import ProxyManager


console = Console()


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
        self._jsonl_position: int = 0  # tracks read position in JSONL file

    # -------------------------------------------------------------------
    # 5.2 / 5.5  run_single
    # -------------------------------------------------------------------

    def run_single(self, run_type: str) -> RunRecord:
        """Guide the user through all sessions/turns for one run condition.

        For each session, displays the session header and each turn prompt
        in a rich Panel. After the user presses Enter (signalling Kiro has
        responded), reads new JSONL entries from the proxy and builds a
        TurnRecord from the captured token data.

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
                # Display the turn prompt in a rich Panel
                console.print(
                    Panel(
                        turn.prompt,
                        title=f"[bold]Turn {turn.turn_number} — {turn.role}[/bold]",
                        border_style="green",
                    )
                )

                # Wait for the user to signal Kiro has responded
                console.print(
                    "[dim]Press Enter after Kiro responds...[/dim]"
                )
                input()

                # 5.5 — Brief pause to let proxy flush, then read new entries
                time.sleep(0.5)
                new_entries, self._jsonl_position = self.proxy.read_new_entries(
                    self._jsonl_position
                )

                # Process entries into a TurnRecord
                turn_record = self._build_turn_record(
                    session.session_id, turn.turn_number, new_entries
                )
                turn_records.append(turn_record)

            # Compute session aggregate
            session_aggregate = compute_session_aggregate(turn_records)
            session_record = SessionRecord(
                session_id=session.session_id,
                task_type=session.task_type,
                turns=turn_records,
                aggregate=session_aggregate,
            )
            session_records.append(session_record)

            # 5.3 — Session boundary: instruct user to start a new chat
            if sess_idx < len(self.script.sessions) - 1:
                console.print()
                console.print(
                    "═══════════════════════════════════════════════════"
                )
                console.print(
                    "  Start a [bold]NEW[/bold] conversation in Kiro for the next session."
                )
                console.print(
                    "  Press Enter when ready..."
                )
                console.print(
                    "═══════════════════════════════════════════════════"
                )
                input()

        # Compute run aggregate
        run_aggregate = compute_run_aggregate(session_records)

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
        """Orchestrate baseline then treatment runs.

        Prints condition setup prompts and waits for user confirmation
        before each run.

        Returns:
            A tuple of (baseline_record, treatment_record).
        """
        # Baseline instructions
        console.print()
        console.print("[bold]BASELINE RUN[/bold]")
        console.print("Ensure NO Powers are active in Kiro.")
        console.print("Press Enter to begin the baseline run...")
        input()

        baseline = self.run_single("baseline")

        # Treatment instructions
        console.print()
        console.print("[bold]TREATMENT RUN[/bold]")
        console.print("Activate the Context Lens Power in Kiro.")
        console.print("Press Enter to begin the treatment run...")
        input()

        treatment = self.run_single("treatment")

        return baseline, treatment

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
