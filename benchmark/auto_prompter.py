#!/usr/bin/env python3
"""Auto-prompter for the AI IDE Token Benchmark.

Uses AppleScript (osascript) on macOS to type prompts into Kiro's chat
window automatically. Monitors the proxy JSONL file to detect when Kiro
has finished responding before sending the next prompt.

Usage:
    # Baseline run (no prefix):
    .venv/bin/python benchmark/auto_prompter.py --config benchmark_config.yaml --run-type baseline

    # Treatment run (with miser-* prefix):
    .venv/bin/python benchmark/auto_prompter.py --config benchmark_config.yaml --run-type treatment

Prerequisites:
    - Kiro must already be open with the target project
    - The mitmproxy proxy must already be running
    - Grant Terminal (or iTerm) accessibility permissions in
      System Preferences > Privacy & Security > Accessibility
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from benchmark.config import load_config
from benchmark.models import DEFAULT_PREFIX_MAP, BenchmarkConfig
from benchmark.session_script import parse_session_script


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------


def _applescript_type_text(text: str) -> None:
    """Use AppleScript to paste text into the frontmost application via clipboard.

    Copies the text to the macOS clipboard using pbcopy, activates Kiro,
    pastes with Cmd+V, then presses Return to send.

    Args:
        text: The text to paste into Kiro's chat.
    """
    # Copy text to clipboard via pbcopy
    proc = subprocess.run(
        ["pbcopy"],
        input=text,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"  [ERROR] pbcopy failed: {proc.stderr.strip()}")
        return

    script = '''
    tell application "Kiro" to activate
    delay 1
    tell application "System Events"
        keystroke "v" using {command down}
        delay 0.5
        keystroke return
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  [ERROR] AppleScript failed: {result.stderr.strip()}")


def _applescript_new_conversation() -> None:
    """Use AppleScript to start a new conversation in Kiro.

    Sends Cmd+Shift+N (or the appropriate shortcut) to open a new chat.
    """
    script = '''
    tell application "Kiro" to activate
    delay 0.5
    tell application "System Events"
        keystroke "n" using {command down}
    end tell
    delay 2
    '''

    subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# JSONL monitoring
# ---------------------------------------------------------------------------


def _get_jsonl_position(jsonl_path: str) -> int:
    """Get the current end position of the JSONL file."""
    if not os.path.exists(jsonl_path):
        return 0
    return os.path.getsize(jsonl_path)


def _wait_for_response(
    jsonl_path: str,
    start_position: int,
    idle_timeout: int = 30,
    turn_timeout: int = 300,
) -> tuple[int, bool]:
    """Wait for Kiro to finish responding by monitoring the JSONL file.

    Args:
        jsonl_path: Path to the proxy JSONL output file.
        start_position: Byte offset to start watching from.
        idle_timeout: Seconds of no new entries before considering done.
        turn_timeout: Max seconds to wait before giving up.

    Returns:
        Tuple of (new_position, timed_out).
    """
    has_received = False
    turn_start = time.monotonic()
    last_activity = time.monotonic()

    while True:
        current_size = os.path.getsize(jsonl_path) if os.path.exists(jsonl_path) else 0

        if current_size > start_position:
            start_position = current_size
            has_received = True
            last_activity = time.monotonic()

        now = time.monotonic()

        # Done: received entries and been idle for idle_timeout
        if has_received and (now - last_activity) >= idle_timeout:
            return start_position, False

        # Timeout: exceeded turn_timeout
        if (now - turn_start) >= turn_timeout:
            return start_position, True

        time.sleep(1)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_prompts(config: BenchmarkConfig, run_type: str) -> None:
    """Run all session prompts through Kiro via AppleScript.

    Args:
        config: The benchmark configuration.
        run_type: Either "baseline" or "treatment".
    """
    # Load session script
    with open(config.prompt_file) as f:
        script = parse_session_script(f.read())

    jsonl_path = os.path.join(config.output_dir, "tokens.jsonl")
    prefix_map = config.automation.treatment_prefix_map
    idle_timeout = config.automation.idle_timeout
    turn_timeout = config.automation.turn_timeout

    total_sessions = len(script.sessions)
    total_turns = sum(len(s.turns) for s in script.sessions)
    completed_turns = 0

    print(f"\n{'='*60}")
    print(f"  {run_type.upper()} RUN — {total_sessions} sessions, {total_turns} turns")
    print(f"  Idle timeout: {idle_timeout}s, Turn timeout: {turn_timeout}s")
    if run_type == "treatment":
        print(f"  Prefix map: {prefix_map}")
    print(f"{'='*60}\n")

    # Give user a moment to switch to Kiro
    print("Starting in 5 seconds — make sure Kiro is visible...")
    time.sleep(5)

    for sess_idx, session in enumerate(script.sessions):
        print(f"\n--- Session {session.session_id}/{total_sessions}: "
              f"{session.title} ({session.task_type}) ---\n")

        for turn in session.turns:
            prompt = turn.prompt

            # Apply prefix for treatment runs
            if run_type == "treatment":
                prefix = prefix_map.get(turn.role, "")
                if prefix:
                    prompt = f"{prefix} {prompt}"
                    print(f"  [Turn {turn.turn_number}] Prefix: {prefix}")

            # Record JSONL position before sending
            position = _get_jsonl_position(jsonl_path)

            # Type the prompt into Kiro
            print(f"  [Turn {turn.turn_number}] Sending prompt ({len(prompt)} chars)...")
            _applescript_type_text(prompt)

            # Wait for response
            print(f"  [Turn {turn.turn_number}] Waiting for response...")
            new_position, timed_out = _wait_for_response(
                jsonl_path, position, idle_timeout, turn_timeout
            )

            completed_turns += 1
            if timed_out:
                print(f"  [Turn {turn.turn_number}] ⚠ TIMED OUT after {turn_timeout}s")
            else:
                elapsed = time.monotonic()  # approximate
                print(f"  [Turn {turn.turn_number}] ✓ Response complete "
                      f"({completed_turns}/{total_turns} turns done)")

        # New conversation between sessions
        if sess_idx < len(script.sessions) - 1:
            print(f"\n  Starting new conversation for next session...")
            _applescript_new_conversation()
            time.sleep(2)

    print(f"\n{'='*60}")
    print(f"  {run_type.upper()} RUN COMPLETE — {completed_turns}/{total_turns} turns")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-prompter: types benchmark prompts into Kiro via AppleScript"
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to benchmark_config.yaml",
    )
    parser.add_argument(
        "--run-type", required=True, choices=["baseline", "treatment"],
        help="Run type: baseline (no prefix) or treatment (with miser-* prefix)",
    )
    parser.add_argument(
        "--start-session", type=int, default=1,
        help="Session number to start from (default: 1, useful for resuming)",
    )
    parser.add_argument(
        "--start-turn", type=int, default=1,
        help="Turn number to start from within the start session (default: 1)",
    )

    args = parser.parse_args()
    config = load_config(args.config)

    # Filter sessions if resuming
    with open(config.prompt_file) as f:
        script = parse_session_script(f.read())

    if args.start_session > 1 or args.start_turn > 1:
        print(f"Resuming from session {args.start_session}, turn {args.start_turn}")

    run_prompts(config, args.run_type)


if __name__ == "__main__":
    main()
