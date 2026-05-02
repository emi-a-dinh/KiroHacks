#!/usr/bin/env python3
"""
miser — smart context for coding agents.

Usage:
    miser fix "fix the auth bypass"
    miser ask "how does auth work?"
    miser plan "add pagination"
    miser tree
    miser index [path]
"""

import argparse
import sys
import os
from pathlib import Path

_src_path = str(Path(__file__).parent)
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)


def _lazy_import(module_path, name):
    import importlib
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        mod = importlib.import_module(f"src.{module_path}")
    return getattr(mod, name)


def _find_repo() -> str:
    cwd = Path.cwd()
    current = cwd
    for _ in range(10):
        if (current / ".git").exists() or (current / ".token-miser").exists():
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


def cmd_fix(args):
    run_fix = _lazy_import("query.smart", "run_fix")
    print(run_fix(args.task, repo_path=_find_repo(), error_log=args.error, k=args.k))

def cmd_ask(args):
    run_ask = _lazy_import("query.smart", "run_ask")
    print(run_ask(args.question, repo_path=_find_repo(), error_log=args.error))

def cmd_plan(args):
    run_plan = _lazy_import("query.smart", "run_plan")
    print(run_plan(args.task, repo_path=_find_repo(), error_log=args.error))

def cmd_index(args):
    run_index = _lazy_import("indexer.core", "run_index")
    result = run_index(args.path or ".")
    print()
    print(f"  {_bold('Indexed')}  {result.files_scanned} files in {result.index_time_seconds}s")
    print(f"    skipped     {result.files_skipped}  {_dim('(unchanged)')}")
    if result.files_moved:
        print(f"    moved       {result.files_moved}")
    print(f"    updated     {result.files_updated}")
    print(f"    units       {result.units_extracted}")
    print(f"    edges       {result.call_edges}")
    print(f"    db          {result.index_path}")
    print()

def cmd_tree(args):
    Database = _lazy_import("storage.db", "Database")
    build_tree_view = _lazy_import("query.tree_view", "build_tree_view")
    repo = _find_repo()
    index_path = str(Path(repo) / ".token-miser" / "index.db")
    if not Path(index_path).exists():
        run_index = _lazy_import("indexer.core", "run_index")
        run_index(repo)
    with Database(index_path) as db:
        print(build_tree_view(db, index_path=index_path, show_edges=not args.no_edges, show_signatures=args.signatures, filter_type=args.type))


def main():
    parser = argparse.ArgumentParser(
        prog="miser",
        description="Token Miser — smart context for coding agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  miser fix "fix the auth bypass on GET task"
  miser ask "how does the login flow work?"
  miser plan "add sorting to the task list"
  miser tree
  miser index

No manual indexing, unit IDs, or expansion needed. Just describe the task.
""",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("fix", help="Select code and get fix instructions")
    p.add_argument("task"); p.add_argument("--error", "-e"); p.add_argument("--k", "-k", type=int, default=10)
    p.set_defaults(func=cmd_fix)

    p = sub.add_parser("ask", help="Ask a question about the codebase")
    p.add_argument("question"); p.add_argument("--error", "-e")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("plan", help="Get an implementation plan")
    p.add_argument("task"); p.add_argument("--error", "-e")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("tree", help="View the unit tree")
    p.add_argument("--no-edges", action="store_true"); p.add_argument("--signatures", "-s", action="store_true")
    p.add_argument("--type", "-t", choices=["function", "method", "class", "constant"])
    p.set_defaults(func=cmd_tree)

    p = sub.add_parser("index", help="Manually re-index")
    p.add_argument("path", nargs="?", default=None)
    p.set_defaults(func=cmd_index)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)

if __name__ == "__main__":
    main()
