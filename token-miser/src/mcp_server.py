#!/usr/bin/env python3
"""MCP server for Token Miser — built on the official MCP Python SDK."""

import sys
from pathlib import Path

# Ensure src/ is on the path for local imports
src_path = str(Path(__file__).parent)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("token-miser")


@mcp.tool()
def miser_fix(task: str, repo_path: str = ".", error_log: str | None = None) -> str:
    """Select relevant code for a bug fix or implementation task.

    Auto-indexes if needed. Returns selected code with fix instructions.

    Args:
        task: What needs to be fixed or implemented.
        repo_path: Path to repo root.
        error_log: Optional error traceback or log.
    """
    from query.smart import run_fix
    return run_fix(task, repo_path=repo_path, error_log=error_log)


@mcp.tool()
def miser_ask(question: str, repo_path: str = ".", error_log: str | None = None) -> str:
    """Answer a question about the codebase.

    Auto-indexes if needed. Returns relevant code. No edits.

    Args:
        question: What you want to know.
        repo_path: Path to repo root.
        error_log: Optional error traceback or log.
    """
    from query.smart import run_ask
    return run_ask(question, repo_path=repo_path, error_log=error_log)


@mcp.tool()
def miser_plan(task: str, repo_path: str = ".", error_log: str | None = None) -> str:
    """Create an implementation plan.

    Auto-indexes if needed. Returns relevant code with planning instructions. No edits.

    Args:
        task: What needs to be built or changed.
        repo_path: Path to repo root.
        error_log: Optional error traceback or log.
    """
    from query.smart import run_plan
    return run_plan(task, repo_path=repo_path, error_log=error_log)


if __name__ == "__main__":
    mcp.run(transport="stdio")
