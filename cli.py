#!/usr/bin/env python3
"""CLI for context-lens indexing operations."""

import argparse
import sys
from pathlib import Path

# Add context-lens/src to path for imports
_src_path = str(Path(__file__).parent / "context-lens" / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)


def main():
    parser = argparse.ArgumentParser(
        description="Context Lens - Code indexing and analysis tool"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # context-index command
    index_parser = subparsers.add_parser(
        "context-index",
        help="Index a repository for code analysis"
    )
    index_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the repository to index (default: current directory)"
    )
    index_parser.add_argument(
        "--index-path",
        "-i",
        help="Custom path for the index database"
    )
    index_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress output except errors"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "context-index":
        # Import here after path is set up
        from indexer.core import run_index
        
        repo_path = Path(args.path).resolve()
        
        if not repo_path.exists():
            print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
            sys.exit(1)
        
        if not repo_path.is_dir():
            print(f"Error: Path is not a directory: {repo_path}", file=sys.stderr)
            sys.exit(1)

        result = run_index(str(repo_path), args.index_path)

        if not args.quiet:
            print(f"Indexed {result.files_scanned} files in {result.index_time_seconds}s")
            print(f"  Updated: {result.files_updated}")
            print(f"  Skipped: {result.files_skipped}")
            print(f"  Moved:   {result.files_moved}")
            print(f"  Deleted: {result.files_deleted}")
            print(f"  Units:   {result.units_extracted}")
            print(f"  Edges:   {result.call_edges}")
            print(f"  Index:   {result.index_path}")


if __name__ == "__main__":
    main()
