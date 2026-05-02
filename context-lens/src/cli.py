#!/usr/bin/env python3
"""Command-line interface for Context Lens."""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from indexer.core import run_index
from indexer.models import IndexResult


def cmd_index(args):
    """Index a repository."""
    result = run_index(args.repo_path, args.index)
    
    print(f"Files scanned:    {result.files_scanned}")
    print(f"Files skipped:    {result.files_skipped}  (unchanged)")
    print(f"Files moved:      {result.files_moved}  (path updated, units preserved)")
    print(f"Files updated:    {result.files_updated}")
    print(f"Files deleted:    {result.files_deleted}")
    print(f"Units extracted:  {result.units_extracted}")
    print(f"Call edges:       {result.call_edges}")
    print(f"Index path:       {result.index_path}")
    print(f"Index time:       {result.index_time_seconds}s")


def cmd_query(args):
    """Generate a signature map."""
    from storage.db import Database
    from query.formatter import build_signature_map
    
    index_path = args.index or ".context-lens/index.db"
    
    if not Path(index_path).exists():
        print(f"Error: Index not found at {index_path}. Run 'context-lens index' first.", file=sys.stderr)
        sys.exit(1)
    
    with Database(index_path) as db:
        signature_map = build_signature_map(db, args.task, args.error, args.k)
        print(signature_map)


def cmd_expand(args):
    """Expand selected units."""
    from storage.db import Database
    from query.expander import build_expanded_prompt
    
    index_path = args.index or ".context-lens/index.db"
    
    if not Path(index_path).exists():
        print(f"Error: Index not found at {index_path}. Run 'context-lens index' first.", file=sys.stderr)
        sys.exit(1)
    
    # Parse unit IDs
    unit_ids = [int(x.strip()) for x in args.unit_ids.split(",")]
    
    with Database(index_path) as db:
        expanded = build_expanded_prompt(
            db, unit_ids, args.task, args.error_summary, args.neighbors
        )
        print(expanded)


def main():
    parser = argparse.ArgumentParser(
        description="Context Lens - Signature-level code indexing for LLM context"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Index command
    index_parser = subparsers.add_parser("index", help="Index a repository")
    index_parser.add_argument("repo_path", nargs="?", default=".", help="Path to repository (default: current directory)")
    index_parser.add_argument("--index", "-i", help="Path to index database")
    index_parser.set_defaults(func=cmd_index)
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Generate a signature map")
    query_parser.add_argument("task", help="Task description")
    query_parser.add_argument("--error", "-e", help="Error log to include")
    query_parser.add_argument("--k", "-k", type=int, default=10, help="Max units to select (default: 10)")
    query_parser.add_argument("--index", "-i", help="Path to index database")
    query_parser.set_defaults(func=cmd_query)
    
    # Expand command
    expand_parser = subparsers.add_parser("expand", help="Expand selected units")
    expand_parser.add_argument("unit_ids", help="Comma-separated list of unit IDs")
    expand_parser.add_argument("--task", "-t", help="Task description")
    expand_parser.add_argument("--error-summary", "-e", help="Error summary")
    expand_parser.add_argument("--neighbors", "-n", action="store_true", help="Include 1-hop neighbors")
    expand_parser.add_argument("--index", "-i", help="Path to index database")
    expand_parser.set_defaults(func=cmd_expand)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
