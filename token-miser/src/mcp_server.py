#!/usr/bin/env python3
"""MCP server for Token Miser — built on the official MCP Python SDK."""

import sys
from pathlib import Path

src_path = str(Path(__file__).parent)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("token-miser")


@mcp.tool()
def miser_context(task: str, repo_path: str = ".", error_log: str | None = None) -> str:
    """Select relevant code units and return signatures only.

    Use this first for any fix, question, or planning task.
    Call miser_read(symbol_name) to fetch full source of any unit shown.

    Args:
        task: What needs to be done or understood.
        repo_path: Path to repo root.
        error_log: Optional error traceback or log.
    """
    if len(task.strip().split()) < 6:
        return (
            "Task description too short to select reliably. "
            "Describe the symptom in a full sentence for best results."
        )
    from query.smart import run_context
    return run_context(task, repo_path=repo_path, error_log=error_log)


@mcp.tool()
def miser_read(symbol_name: str, repo_path: str = ".") -> str:
    """Return full source of a single indexed unit by symbol name.

    Call this after miser_context to expand a specific function or class.

    Args:
        symbol_name: Exact or partial symbol name (e.g. "createIdea", "require_auth").
        repo_path: Path to repo root.
    """
    from query.smart import run_read
    return run_read(symbol_name, repo_path=repo_path)


if __name__ == "__main__":
    mcp.run(transport="stdio")
