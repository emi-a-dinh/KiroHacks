"""Automation driver for the AI IDE Token Benchmark.

Contains the PowerManager class for managing the token-miser Power state
between baseline and treatment runs, the PromptSender class for delivering
prompts to Kiro's stdin with optional treatment prefixing, and the
ResponseWatcher class for detecting when Kiro has finished responding.
Additional classes (AutomationDriver) will be added in later tasks.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import subprocess
import time
from typing import Dict, List, Tuple

from benchmark.models import BenchmarkConfig, BenchmarkError, DEFAULT_PREFIX_MAP, WatchResult
from benchmark.proxy import ProxyManager

logger = logging.getLogger(__name__)


class PowerManager:
    """Manages the token-miser Power state by modifying MCP config and steering files.

    Disables the Power for baseline runs and enables it for treatment runs.
    Backs up original file contents and restores them when the benchmark completes.

    Args:
        repo_path: Path to the target repository (used for context, but .kiro
            paths are resolved relative to the current working directory since
            .kiro lives in the workspace root, not inside the target repo).
    """

    def __init__(self, repo_path: str) -> None:
        self.repo_path = repo_path
        # Resolve .kiro paths relative to the current working directory
        cwd = os.getcwd()
        self.mcp_config_path = os.path.join(cwd, ".kiro", "settings", "mcp.json")
        self.steering_path = os.path.join(cwd, ".kiro", "steering", "token-miser.md")
        self.steering_disabled_path = self.steering_path + ".disabled"

        self._mcp_config_backup: str | None = None
        self._steering_backup: str | None = None

    def backup(self) -> None:
        """Read and store original contents of MCP config and steering file.

        Raises:
            FileNotFoundError: If the MCP config file does not exist.
        """
        # MCP config is required — raise if missing
        if not os.path.exists(self.mcp_config_path):
            raise FileNotFoundError(
                f"MCP config file not found: {self.mcp_config_path}"
            )
        with open(self.mcp_config_path, "r") as f:
            self._mcp_config_backup = f.read()
        logger.info("Backed up MCP config from %s", self.mcp_config_path)

        # Steering file is optional — log warning if missing
        if os.path.exists(self.steering_path):
            with open(self.steering_path, "r") as f:
                self._steering_backup = f.read()
            logger.info("Backed up steering file from %s", self.steering_path)
        else:
            logger.warning(
                "Steering file not found: %s — skipping backup", self.steering_path
            )
            self._steering_backup = None

    def disable_power(self) -> None:
        """Disable the token-miser Power for baseline runs.

        Sets ``"disabled": true`` in mcp.json for the token-miser server entry
        and renames the steering file to ``.disabled``.
        """
        # Update mcp.json to disable token-miser
        with open(self.mcp_config_path, "r") as f:
            config = json.load(f)

        config["mcpServers"]["token-miser"]["disabled"] = True

        with open(self.mcp_config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        logger.info("Disabled token-miser in MCP config")

        # Rename steering file to .disabled
        if os.path.exists(self.steering_path):
            os.rename(self.steering_path, self.steering_disabled_path)
            logger.info("Renamed steering file to %s", self.steering_disabled_path)
        else:
            logger.warning(
                "Steering file not found for disabling: %s", self.steering_path
            )

    def enable_power(self) -> None:
        """Enable the token-miser Power for treatment runs.

        Sets ``"disabled": false`` in mcp.json for the token-miser server entry
        and restores the steering file from ``.disabled``.
        """
        # Update mcp.json to enable token-miser
        with open(self.mcp_config_path, "r") as f:
            config = json.load(f)

        config["mcpServers"]["token-miser"]["disabled"] = False

        with open(self.mcp_config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        logger.info("Enabled token-miser in MCP config")

        # Restore steering file from .disabled
        if os.path.exists(self.steering_disabled_path):
            os.rename(self.steering_disabled_path, self.steering_path)
            logger.info("Restored steering file from %s", self.steering_disabled_path)
        else:
            logger.warning(
                "Disabled steering file not found for restoring: %s",
                self.steering_disabled_path,
            )

    def restore(self) -> None:
        """Restore MCP config and steering file to their original pre-benchmark state.

        Uses the in-memory backups created by :meth:`backup`. Catches ``OSError``
        and logs for manual recovery if file writes fail.
        """
        if self._mcp_config_backup is not None:
            try:
                with open(self.mcp_config_path, "w") as f:
                    f.write(self._mcp_config_backup)
                logger.info("Restored MCP config to %s", self.mcp_config_path)
            except OSError as e:
                logger.error(
                    "Failed to restore MCP config to %s: %s. "
                    "Manual recovery needed. Original content:\n%s",
                    self.mcp_config_path,
                    e,
                    self._mcp_config_backup,
                )

        if self._steering_backup is not None:
            try:
                # Remove the .disabled version if it exists
                if os.path.exists(self.steering_disabled_path):
                    os.remove(self.steering_disabled_path)
                with open(self.steering_path, "w") as f:
                    f.write(self._steering_backup)
                logger.info("Restored steering file to %s", self.steering_path)
            except OSError as e:
                logger.error(
                    "Failed to restore steering file to %s: %s. "
                    "Manual recovery needed. Original content:\n%s",
                    self.steering_path,
                    e,
                    self._steering_backup,
                )


class PromptSender:
    """Delivers prompts to Kiro's stdin with optional treatment prefixing.

    For baseline runs, prompts are written verbatim. For treatment runs,
    each prompt is prefixed with the appropriate MCP tool command based on
    the turn's role, using the Treatment_Prefix_Map.

    Args:
        kiro_process: The Kiro subprocess whose stdin receives prompts.
        prefix_map: Mapping from turn role to MCP tool prefix. Defaults
            to ``DEFAULT_PREFIX_MAP`` if not provided.
    """

    def __init__(
        self,
        kiro_process: subprocess.Popen,
        prefix_map: Dict[str, str] = None,
    ) -> None:
        self._process = kiro_process
        self._prefix_map = prefix_map if prefix_map is not None else dict(DEFAULT_PREFIX_MAP)

    def send(self, prompt: str, run_type: str = "baseline", role: str = "") -> None:
        """Send a prompt to the Kiro process's stdin.

        For ``run_type="baseline"``, the prompt is written verbatim followed
        by a newline. For ``run_type="treatment"``, the prompt is first
        prefixed via :meth:`_apply_prefix` before writing.

        Args:
            prompt: The prompt text to send.
            run_type: Either ``"baseline"`` or ``"treatment"``.
            role: The turn role (e.g. ``"task_description"``), used for
                prefix lookup during treatment runs.

        Raises:
            BrokenPipeError: If the Kiro process has exited and the pipe
                is broken.
        """
        try:
            if run_type == "treatment":
                prefixed_prompt = self._apply_prefix(prompt, role)
                self._process.stdin.write(prefixed_prompt + "\n")
            else:
                self._process.stdin.write(prompt + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise BrokenPipeError(
                f"Failed to write to Kiro process stdin: {e}"
            ) from e

    def _apply_prefix(self, prompt: str, role: str) -> str:
        """Prepend the MCP tool prefix for the given role to the prompt.

        Args:
            prompt: The original prompt text.
            role: The turn role to look up in the prefix map.

        Returns:
            The prefixed prompt string ``"{prefix} {prompt}"`` if the role
            is found, or the original prompt verbatim if not found.
        """
        prefix = self._prefix_map.get(role)
        if prefix is not None:
            logger.info("Applying prefix '%s' for role '%s'", prefix, role)
            return f"{prefix} {prompt}"
        else:
            logger.warning(
                "No prefix found for role '%s' — delivering prompt verbatim",
                role,
            )
            return prompt


class ResponseWatcher:
    """Monitors the proxy JSONL file to detect when Kiro has finished responding.

    Uses a dual-timer approach:
    - **Idle timer**: Resets each time new entries appear. When it exceeds
      ``idle_timeout`` after at least one entry has been received, the turn
      is considered complete.
    - **Turn timer**: Starts when ``wait_for_response`` is called. If it
      exceeds ``turn_timeout`` without the idle condition being met, the
      turn is marked as timed out.

    Args:
        proxy: The ProxyManager instance used to read JSONL entries.
        idle_timeout: Seconds of JSONL silence after which a turn is
            considered complete (once at least one entry has arrived).
        turn_timeout: Maximum seconds to wait for a turn to complete
            before marking it as timed out.
    """

    def __init__(self, proxy: ProxyManager, idle_timeout: int, turn_timeout: int) -> None:
        self._proxy = proxy
        self._idle_timeout = idle_timeout
        self._turn_timeout = turn_timeout

    def wait_for_response(self, start_position: int) -> WatchResult:
        """Poll for new JSONL entries until the turn is complete or times out.

        Polls ``proxy.read_new_entries(start_position)`` in a loop at
        1-second intervals. Accumulates all entries across poll iterations.

        The turn is considered complete when:
        - At least one entry has been received, AND
        - No new entries have appeared for ``idle_timeout`` seconds.

        The turn is marked as timed out when:
        - ``turn_timeout`` seconds have elapsed since this method was called
          without the idle completion condition being met.

        Uses ``time.monotonic()`` for timing to avoid clock skew issues.

        Args:
            start_position: The byte offset in the JSONL file to start
                reading from.

        Returns:
            A ``WatchResult`` with all accumulated entries, the new file
            position, and whether the turn timed out.
        """
        all_entries: List[dict] = []
        current_position = start_position
        has_received_entries = False

        turn_start = time.monotonic()
        last_activity = time.monotonic()

        while True:
            new_entries, new_position = self._proxy.read_new_entries(current_position)

            if new_entries:
                all_entries.extend(new_entries)
                current_position = new_position
                has_received_entries = True
                last_activity = time.monotonic()

            now = time.monotonic()

            # Check idle timeout: turn complete if we've received entries
            # and been idle for idle_timeout seconds
            if has_received_entries and (now - last_activity) >= self._idle_timeout:
                logger.info(
                    "Turn complete: idle timeout reached after %d entries",
                    len(all_entries),
                )
                return WatchResult(
                    entries=all_entries,
                    new_position=current_position,
                    timed_out=False,
                )

            # Check turn timeout: give up if total time exceeds turn_timeout
            if (now - turn_start) >= self._turn_timeout:
                logger.warning(
                    "Turn timed out after %d seconds with %d entries",
                    self._turn_timeout,
                    len(all_entries),
                )
                return WatchResult(
                    entries=all_entries,
                    new_position=current_position,
                    timed_out=True,
                )

            time.sleep(1)


class AutomationDriver:
    """Top-level coordinator that manages the Kiro subprocess lifecycle and drives
    the prompt/response loop.

    Launches Kiro as a subprocess with proxy environment variables, delivers prompts
    via ``PromptSender``, and detects response completion via ``ResponseWatcher``.

    Args:
        proxy: The ProxyManager instance for reading JSONL entries.
        config: The BenchmarkConfig with automation settings.
    """

    def __init__(self, proxy: ProxyManager, config: BenchmarkConfig) -> None:
        self._proxy = proxy
        self._config = config
        self._kiro_process: subprocess.Popen | None = None
        self._prompt_sender: PromptSender | None = None
        self._response_watcher = ResponseWatcher(
            proxy,
            config.automation.idle_timeout,
            config.automation.turn_timeout,
        )
        self._jsonl_position: int = 0
        self._consecutive_timeouts: int = 0
        self._restart_count: int = 0

    def start_kiro(self) -> None:
        """Launch the Kiro process as a subprocess with proxy environment variables.

        Sets ``HTTPS_PROXY``, ``HTTP_PROXY``, and ``NODE_TLS_REJECT_UNAUTHORIZED=0``
        so that Kiro's traffic is routed through the benchmark proxy.

        Waits up to ``config.automation.startup_timeout`` seconds for the process
        to remain alive (polls ``process.poll()`` every 1 second).

        Raises:
            BenchmarkError: If the process exits during startup.
        """
        env = os.environ.copy()
        env["HTTPS_PROXY"] = f"http://localhost:{self._config.proxy_port}"
        env["HTTP_PROXY"] = f"http://localhost:{self._config.proxy_port}"
        env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"

        self._kiro_process = subprocess.Popen(
            [self._config.automation.kiro_path, self._config.repo_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        startup_timeout = self._config.automation.startup_timeout
        for _ in range(startup_timeout):
            if self._kiro_process.poll() is not None:
                stderr_output = self._kiro_process.stderr.read() if self._kiro_process.stderr else ""
                exit_code = self._kiro_process.returncode
                self._kiro_process = None
                raise BenchmarkError(
                    f"Kiro process exited during startup with code {exit_code}: {stderr_output}"
                )
            time.sleep(1)

        self._prompt_sender = PromptSender(
            self._kiro_process,
            self._config.automation.treatment_prefix_map,
        )
        logger.info("Kiro process started (PID %d)", self._kiro_process.pid)

    def stop_kiro(self) -> None:
        """Stop the Kiro process gracefully.

        Sends SIGTERM first, waits 5 seconds, then SIGKILL if needed.
        Mirrors the pattern in ``ProxyManager.stop()``.
        """
        if self._kiro_process is None:
            return

        try:
            self._kiro_process.send_signal(signal.SIGTERM)
            self._kiro_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._kiro_process.kill()
            self._kiro_process.wait(timeout=2)
        except OSError:
            pass  # Process already exited
        finally:
            self._kiro_process = None
            self._prompt_sender = None

    def new_conversation(self) -> None:
        """Stop the current Kiro process and start a new one for a clean session context."""
        self.stop_kiro()
        self.start_kiro()

    def reset_restart_count(self) -> None:
        """Reset restart and consecutive timeout counters.

        Called by the Orchestrator at the start of each run (baseline/treatment)
        so the restart limit is per-run, not per-benchmark.
        """
        self._restart_count = 0
        self._consecutive_timeouts = 0

    def _handle_restart(self, session_id: int, turn_number: int) -> None:
        """Attempt a Kiro restart after consecutive unresponsive turns.

        Increments the restart count and checks against the maximum limit.
        If the limit is exceeded, raises ``BenchmarkError``. Otherwise,
        logs the restart event, starts a new conversation, and resets the
        consecutive timeout counter.

        Args:
            session_id: The current session ID for logging.
            turn_number: The current turn number for logging.

        Raises:
            BenchmarkError: If the maximum restart limit (2) has been exceeded.
        """
        self._restart_count += 1
        if self._restart_count > 2:
            raise BenchmarkError("Max restarts exceeded (2 per run)")
        logger.warning(
            "Restarting Kiro process (restart %d/2) at session %d, turn %d",
            self._restart_count,
            session_id,
            turn_number,
        )
        self.new_conversation()
        self._consecutive_timeouts = 0

    def run_turn(
        self,
        prompt: str,
        run_type: str = "baseline",
        role: str = "",
        session_id: int = 0,
        turn_number: int = 0,
    ) -> Tuple[List[dict], bool]:
        """Send a prompt and wait for the response.

        Checks Kiro health first, sends the prompt via ``PromptSender``,
        then waits for the response via ``ResponseWatcher``. Tracks
        consecutive timeouts with zero entries and triggers a Kiro restart
        after 3 consecutive unresponsive turns.

        Also handles ``BrokenPipeError`` from the prompt sender — if the
        pipe is broken (Kiro process exited), it is treated as an
        unresponsive turn and triggers the same restart logic.

        Args:
            prompt: The prompt text to send.
            run_type: Either ``"baseline"`` or ``"treatment"``.
            role: The turn role for prefix lookup during treatment runs.
            session_id: The current session ID for logging during restarts.
            turn_number: The current turn number for logging during restarts.

        Returns:
            A tuple of ``(entries, timed_out)`` where entries is the list
            of JSONL entries captured during this turn and timed_out indicates
            whether the turn exceeded the turn timeout.

        Raises:
            BenchmarkError: If the Kiro process is not running and cannot
                be restarted, or if max restarts are exceeded.
        """
        if not self.check_health():
            raise BenchmarkError("Kiro process is not running")

        # Attempt to send the prompt; handle broken pipe as unresponsive turn
        try:
            self._prompt_sender.send(prompt, run_type, role)
        except BrokenPipeError:
            logger.error(
                "Broken pipe writing to Kiro stdin at session %d, turn %d",
                session_id,
                turn_number,
            )
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= 3:
                self._handle_restart(session_id, turn_number)
            return ([], True)

        result = self._response_watcher.wait_for_response(self._jsonl_position)
        self._jsonl_position = result.new_position

        # Track consecutive timeouts with zero entries
        if result.timed_out and len(result.entries) == 0:
            self._consecutive_timeouts += 1
        else:
            self._consecutive_timeouts = 0

        # Check if we need to restart after 3 consecutive unresponsive turns
        if self._consecutive_timeouts >= 3:
            self._handle_restart(session_id, turn_number)

        return (result.entries, result.timed_out)

    def check_health(self) -> bool:
        """Check if the Kiro process is still running.

        Returns:
            ``True`` if the Kiro process is alive, ``False`` otherwise.
        """
        return self._kiro_process is not None and self._kiro_process.poll() is None
