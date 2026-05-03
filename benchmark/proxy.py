"""Proxy management for the AI IDE Token Benchmark.

Manages the mitmproxy (mitmdump) subprocess and provides methods to read
captured token data from the JSONL output file.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


# Path to the addon template bundled with this package
_ADDON_TEMPLATE_PATH = Path(__file__).parent / "_addon_template.py"


class ProxyManager:
    """Manages the mitmdump proxy subprocess and JSONL token log.

    Args:
        port: The port for mitmdump to listen on.
        jsonl_path: Path to the JSONL file where the addon writes token data.
    """

    def __init__(self, port: int, jsonl_path: str) -> None:
        self.port = port
        self.jsonl_path = jsonl_path
        self._process: subprocess.Popen | None = None
        self._temp_addon_path: str | None = None

    def start(self) -> None:
        """Start the mitmdump proxy subprocess.

        Copies the addon template to a temp file and launches mitmdump
        with the appropriate arguments. The BENCHMARK_JSONL_PATH env var
        is set so the addon knows where to write.

        Raises:
            FileNotFoundError: If mitmdump is not found on PATH.
            RuntimeError: If the proxy is already running.
        """
        if self._process is not None:
            raise RuntimeError("Proxy is already running.")

        # Verify mitmdump is available — check venv bin first, then system PATH
        mitmdump_path = shutil.which("mitmdump")
        if mitmdump_path is None:
            # Check if mitmdump lives next to the current Python interpreter
            venv_bin = os.path.dirname(sys.executable)
            candidate = os.path.join(venv_bin, "mitmdump")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                mitmdump_path = candidate
            else:
                raise FileNotFoundError(
                    "mitmdump not found on PATH. Install mitmproxy: pip install mitmproxy"
                )

        # Copy addon template to a temp file
        fd, self._temp_addon_path = tempfile.mkstemp(suffix=".py", prefix="benchmark_addon_")
        with os.fdopen(fd, "w") as tmp:
            with open(_ADDON_TEMPLATE_PATH, "r") as src:
                tmp.write(src.read())

        # Ensure the JSONL output directory exists
        jsonl_dir = os.path.dirname(self.jsonl_path)
        if jsonl_dir:
            os.makedirs(jsonl_dir, exist_ok=True)

        # Build the mitmdump command
        cmd = [
            mitmdump_path,
            "--listen-port", str(self.port),
            "--scripts", self._temp_addon_path,
            "--set", f"confdir={os.path.expanduser('~/.mitmproxy')}",
        ]

        # Set up environment with the JSONL path
        env = os.environ.copy()
        env["BENCHMARK_JSONL_PATH"] = self.jsonl_path

        self._process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the mitmdump proxy subprocess gracefully.

        Sends SIGTERM first, then SIGKILL after the timeout if the process
        hasn't exited.

        Args:
            timeout: Seconds to wait after SIGTERM before sending SIGKILL.
        """
        if self._process is None:
            return

        try:
            self._process.send_signal(signal.SIGTERM)
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=2)
        except OSError:
            pass  # Process already exited
        finally:
            self._process = None

        # Clean up temp addon file
        if self._temp_addon_path and os.path.exists(self._temp_addon_path):
            try:
                os.unlink(self._temp_addon_path)
            except OSError:
                pass
            self._temp_addon_path = None

    def read_entries(self) -> List[dict]:
        """Read all entries from the JSONL file.

        Returns:
            A list of parsed JSON dicts, one per line. Malformed lines
            are silently skipped.
        """
        entries: List[dict] = []
        if not os.path.exists(self.jsonl_path):
            return entries

        with open(self.jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return entries

    def read_new_entries(self, last_position: int) -> Tuple[List[dict], int]:
        """Read only new entries from the JSONL file since last_position.

        Args:
            last_position: The byte offset to start reading from.

        Returns:
            A tuple of (new_entries, new_position) where new_position is
            the byte offset after the last read line.
        """
        entries: List[dict] = []
        if not os.path.exists(self.jsonl_path):
            return entries, last_position

        with open(self.jsonl_path, "r") as f:
            f.seek(last_position)
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
            new_position = f.tell()

        return entries, new_position


def print_proxy_instructions(port: int) -> None:
    """Print instructions for configuring the system proxy.

    Uses rich for formatted terminal output. Covers macOS system proxy
    setup, mitmproxy CA certificate installation, and verification steps.

    Args:
        port: The proxy port number.
    """
    console = Console()

    console.print()

    # Step 1: System proxy setup
    step1 = Text()
    step1.append("Set macOS system proxy:\n\n", style="bold")
    step1.append(f"  networksetup -setwebproxy Wi-Fi localhost {port}\n")
    step1.append(f"  networksetup -setsecurewebproxy Wi-Fi localhost {port}\n\n")
    step1.append("To disable later:\n\n", style="dim")
    step1.append("  networksetup -setwebproxystate Wi-Fi off\n")
    step1.append("  networksetup -setsecurewebproxystate Wi-Fi off\n")

    console.print(Panel(step1, title="[bold cyan]Step 1: Configure System Proxy[/]", border_style="cyan"))

    # Step 2: CA certificate (first time only)
    step2 = Text()
    step2.append("First time only — install the mitmproxy CA certificate:\n\n", style="bold")
    step2.append("  1. Start mitmproxy once to generate certs:\n")
    step2.append("     mitmdump --listen-port 0 &\n")
    step2.append("     kill %1\n\n")
    step2.append("  2. Install the CA certificate:\n")
    step2.append("     sudo security add-trusted-cert -d -r trustRoot \\\n")
    step2.append("       -k /Library/Keychains/System.keychain \\\n")
    step2.append("       ~/.mitmproxy/mitmproxy-ca-cert.pem\n\n")
    step2.append("  Or open ~/.mitmproxy/mitmproxy-ca-cert.pem in Keychain Access\n")
    step2.append("  and set it to 'Always Trust'.\n")

    console.print(Panel(step2, title="[bold yellow]Step 2: Install CA Certificate (first time)[/]", border_style="yellow"))

    # Step 3: Verify
    step3 = Text()
    step3.append("Verify the proxy is working:\n\n", style="bold")
    step3.append(f"  curl -x http://localhost:{port} https://httpbin.org/get\n\n")
    step3.append("You should see a JSON response. If you get a certificate error,\n")
    step3.append("make sure the mitmproxy CA cert is installed and trusted.\n")

    console.print(Panel(step3, title="[bold green]Step 3: Verify Proxy[/]", border_style="green"))

    console.print()
