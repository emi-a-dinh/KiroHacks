#!/usr/bin/env python3
"""MCP server for Token Miser."""

import sys
from pathlib import Path

SRC_PATH = str(Path(__file__).resolve().parent)
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("token-miser")


def _require_descriptive_task(task: str) -> str | None:
    if len(task.strip().split()) >= 6:
        return None
    return (
        "Task description too short to select reliably. "
        "Describe the symptom or goal in a full sentence."
    )


@mcp.tool()
def miser_context(task: str, repo_path: str = ".", error_log: str | None = None, k: int = 5) -> str:
    """Select relevant code units and return signatures only."""
    error = _require_descriptive_task(task)
    if error:
        return error
    from query.smart import run_context

    return run_context(task, repo_path=repo_path, error_log=error_log, k=k)


@mcp.tool()
def miser_read(symbol_name: str, repo_path: str = ".") -> str:
    """Return full source of a single indexed unit by symbol name."""
    from query.smart import run_read

    return run_read(symbol_name, repo_path=repo_path)


@mcp.tool()
def miser_fix(task: str, repo_path: str = ".", error_log: str | None = None, k: int = 12) -> str:
    """Select focused code context for an implementation or bug-fix task."""
    error = _require_descriptive_task(task)
    if error:
        return error
    from query.smart import run_fix

    return run_fix(task, repo_path=repo_path, error_log=error_log, k=k)


@mcp.tool()
def miser_ask(question: str, repo_path: str = ".", error_log: str | None = None, k: int = 8) -> str:
    """Select focused code context for a codebase question."""
    error = _require_descriptive_task(question)
    if error:
        return error
    from query.smart import run_ask

    return run_ask(question, repo_path=repo_path, error_log=error_log, k=k)


@mcp.tool()
def miser_plan(task: str, repo_path: str = ".", error_log: str | None = None, k: int = 10) -> str:
    """Select focused code context for planning a change."""
    error = _require_descriptive_task(task)
    if error:
        return error
    from query.smart import run_plan

    return run_plan(task, repo_path=repo_path, error_log=error_log, k=k)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
