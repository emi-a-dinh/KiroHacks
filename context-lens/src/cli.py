#!/usr/bin/env python3
"""
lens — smart context for coding agents.

Usage:
    lens fix "fix the auth bypass"      Select code, get fix instructions
    lens ask "how does auth work?"      Select code, get explanation
    lens plan "add pagination"          Select code, get implementation plan
    lens tree                           Browse the unit tree
    lens index [path]                   Manually re-index
"""

import argparse
import sys
import os
from pathlib import Path

# Support both direct execution (python src/cli.py) and package install (lens)
_src_path = str(Path(__file__).parent)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)


def _lazy_import(module_path, name):
    """Import from either package or direct path."""
    import importlib
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        mod = importlib.import_module(f"src.{module_path}")
    return getattr(mod, name)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_repo() -> str:
    """Find the repo root by looking for .git or .context-lens."""
    cwd = Path.cwd()
    current = cwd
    for _ in range(10):
        if (current / ".git").exists() or (current / ".context-lens").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return str(cwd)


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _bold(t):
    return f"\033[1m{t}\033[0m" if _supports_color() else t


def _dim(t):
    return f"\033[2m{t}\033[0m" if _supports_color() else t


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_fix(args):
    """Select relevant code and return fix instructions."""
    run_fix = _lazy_import("query.smart", "run_fix")
    repo = _find_repo()
    result = run_fix(args.task, repo_path=repo, error_log=args.error, k=args.k)
    print(result)


def cmd_ask(args):
    """Select relevant code and return an explanation prompt."""
    run_ask = _lazy_import("query.smart", "run_ask")
    repo = _find_repo()
    result = run_ask(args.question, repo_path=repo, error_log=args.error)
    print(result)


def cmd_plan(args):
    """Select relevant code and return an implementation plan prompt."""
    run_plan = _lazy_import("query.smart", "run_plan")
    repo = _find_repo()
    result = run_plan(args.task, repo_path=repo, error_log=args.error)
    print(result)


def cmd_index(args):
    """Manually index a repository."""
    run_index = _lazy_import("indexer.core", "run_index")
    repo_path = args.path or "."
    result = run_index(repo_path)

    print()
    print(f"  {_bold('Indexed')}  {result.files_scanned} files in {result.index_time_seconds}s")
    print()
    print(f"    scanned     {result.files_scanned}")
    print(f"    skipped     {result.files_skipped}  {_dim('(unchanged)')}")
    if result.files_moved:
        print(f"    moved       {result.files_moved}  {_dim('(path updated)')}")
    print(f"    updated     {result.files_updated}")
    if result.files_deleted:
        print(f"    deleted     {result.files_deleted}")
    print()
    print(f"    units       {result.units_extracted}")
    print(f"    edges       {result.call_edges}")
    print(f"    db          {result.index_path}")
    print()


def cmd_tree(args):
    """Render the index as a terminal tree."""
    Database = _lazy_import("storage.db", "Database")
    build_tree_view = _lazy_import("query.tree_view", "build_tree_view")

    # Find index
    repo = _find_repo()
    index_path = str(Path(repo) / ".context-lens" / "index.db")

    if not Path(index_path).exists():
        # Auto-index if missing
        run_index = _lazy_import("indexer.core", "run_index")
        run_index(repo)

    with Database(index_path) as db:
        tree = build_tree_view(
            db,
            index_path=index_path,
            show_edges=not args.no_edges,
            show_signatures=args.signatures,
            filter_type=args.type,
        )
        print(tree)


# ── Argument parser ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="lens",
        description="Smart context for coding agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
       
    )

    sub = parser.add_subparsers(dest="command")

    # ── lens fix ───────────────────────────────────────────────────────────
    p_fix = sub.add_parser("fix", help="Select code and get fix instructions")
    p_fix.add_argument("task", help="What needs to be fixed")
    p_fix.add_argument("--error", "-e", help="Error log or traceback")
    p_fix.add_argument("--k", "-k", type=int, default=10, help="Target number of units (default: 10)")
    p_fix.set_defaults(func=cmd_fix)

    # ── lens ask ───────────────────────────────────────────────────────────
    p_ask = sub.add_parser("ask", help="Ask a question about the codebase")
    p_ask.add_argument("question", help="What you want to know")
    p_ask.add_argument("--error", "-e", help="Error log or traceback")
    p_ask.set_defaults(func=cmd_ask)

    # ── lens plan ──────────────────────────────────────────────────────────
    p_plan = sub.add_parser("plan", help="Get an implementation plan")
    p_plan.add_argument("task", help="What needs to be built")
    p_plan.add_argument("--error", "-e", help="Error log or traceback")
    p_plan.set_defaults(func=cmd_plan)

    # ── lens tree ──────────────────────────────────────────────────────────
    p_tree = sub.add_parser("tree", help="View the unit tree")
    p_tree.add_argument("--no-edges", action="store_true", help="Hide edge counts")
    p_tree.add_argument("--signatures", "-s", action="store_true", help="Show full signatures")
    p_tree.add_argument("--type", "-t", choices=["function", "method", "class", "constant"], help="Filter by type")
    p_tree.set_defaults(func=cmd_tree)

    # ── lens index ─────────────────────────────────────────────────────────
    p_index = sub.add_parser("index", help="Manually re-index a repository")
    p_index.add_argument("path", nargs="?", default=None, help="Path to repo (default: current directory)")
    p_index.set_defaults(func=cmd_index)

    # ── No command → show help ─────────────────────────────────────────────
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
