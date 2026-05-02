"""Core indexing logic."""

import time
from pathlib import Path
from typing import List, Optional

from .models import CodeUnit, FileInfo, IndexResult
from .scanner import scan_repository, detect_moves
from .parser_python import parse_python_file
from .parser_treesitter import parse_with_treesitter, TREE_SITTER_AVAILABLE
from .parser_regex import parse_with_regex
from .edge_builder import build_edges


def parse_file(file_path: str, source: str, language: str) -> List[CodeUnit]:
    """
    Parse a file and extract code units.
    
    Tries tree-sitter first, falls back to language-specific parsers,
    then to regex as a last resort.
    """
    units: List[CodeUnit] = []
    
    # Try tree-sitter first
    if TREE_SITTER_AVAILABLE:
        units = parse_with_treesitter(file_path, source, language)
        if units:
            return units
    
    # Fall back to Python AST for Python files
    if language == "python":
        units = parse_python_file(file_path, source)
        if units:
            return units
    
    # Fall back to regex
    units = parse_with_regex(file_path, source, language)
    return units


def run_index(repo_path: str, index_path: Optional[str] = None) -> IndexResult:
    """
    Index a repository.
    
    Args:
        repo_path: Path to the repository root
        index_path: Optional path to the index database.
                   Defaults to <repo_path>/.context-lens/index.db
                   
    Returns:
        IndexResult with statistics about the indexing operation
    """
    # Import Database here to avoid circular imports
    import sys
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from storage.db import Database
    
    start_time = time.time()
    result = IndexResult()
    
    repo = Path(repo_path).resolve()
    
    # Determine index path
    if index_path is None:
        index_path = str(repo / ".context-lens" / "index.db")
    result.index_path = index_path
    
    # Open database
    with Database(index_path) as db:
        # Get existing files from DB
        existing_files = db.get_all_files()  # path -> hash
        
        # Scan repository
        scanned_files = scan_repository(str(repo))
        result.files_scanned = len(scanned_files)
        
        # Build lookup for scanned files
        scanned_lookup = {f.file_path: f for f in scanned_files}
        scanned_hashes = {f.file_path: f.file_hash for f in scanned_files}
        
        # Determine what changed
        existing_paths = set(existing_files.keys())
        scanned_paths = set(scanned_lookup.keys())
        
        # Paths in DB but not on disk (potentially deleted or moved)
        orphaned_paths = existing_paths - scanned_paths
        # Paths on disk but not in DB (potentially new or moved)
        new_paths = scanned_paths - existing_paths
        # Paths in both
        common_paths = existing_paths & scanned_paths
        
        # Detect moves
        orphaned_hashes = {p: existing_files[p] for p in orphaned_paths}
        new_hashes = {p: scanned_hashes[p] for p in new_paths}
        moves = detect_moves(orphaned_hashes, new_hashes)
        
        # Process moves
        moved_old_paths = set()
        moved_new_paths = set()
        for old_path, new_path in moves:
            db.update_file_path(old_path, new_path)
            moved_old_paths.add(old_path)
            moved_new_paths.add(new_path)
            result.files_moved += 1
        
        # Update orphaned and new sets after moves
        orphaned_paths -= moved_old_paths
        new_paths -= moved_new_paths
        
        # Delete truly orphaned files
        for path in orphaned_paths:
            db.delete_file(path)
            result.files_deleted += 1
        
        # Check for changed files (same path, different hash)
        changed_paths = set()
        for path in common_paths:
            if existing_files[path] != scanned_hashes[path]:
                changed_paths.add(path)
        
        # Files to process (new + changed)
        paths_to_process = new_paths | changed_paths
        
        # Skip unchanged files
        result.files_skipped = len(common_paths - changed_paths)
        
        # Process files that need updating
        for path in paths_to_process:
            file_info = scanned_lookup[path]
            
            # Read file content
            full_path = repo / path
            try:
                source = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            
            # Delete old units if this is an update
            if path in changed_paths:
                db.delete_units_for_file(path)
            
            # Upsert file record
            db.upsert_file(file_info)
            
            # Parse and extract units
            units = parse_file(path, source, file_info.language or "")
            
            # Insert units
            for unit in units:
                unit.unit_id = db.insert_unit(unit)
            
            result.files_updated += 1
        
        db.commit()
        
        # Rebuild edges (always rebuild from scratch for simplicity)
        all_units = db.get_all_units()
        result.units_extracted = len(all_units)
        
        db.clear_edges()
        edges = build_edges(all_units)
        db.insert_edges(edges)
        result.call_edges = len(edges)
        
        db.commit()
    
    result.index_time_seconds = round(time.time() - start_time, 2)
    return result
