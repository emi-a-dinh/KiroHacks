"""File system scanner for the indexer."""

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .models import FileInfo

# Directories to skip
SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "eggs",
    "*.egg-info",
    ".eggs",
    "target",  # Rust/Java
    "vendor",  # Go
}

# File extensions to index
SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
}

# Max file size to index (500KB)
MAX_FILE_SIZE = 500 * 1024


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_language(file_path: Path) -> str | None:
    """Detect language from file extension."""
    return SOURCE_EXTENSIONS.get(file_path.suffix.lower())


def should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped."""
    return dir_name in SKIP_DIRS or dir_name.startswith(".")


def is_binary_file(file_path: Path) -> bool:
    """Check if a file appears to be binary."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            # Check for null bytes (common in binary files)
            if b"\x00" in chunk:
                return True
            # Try to decode as UTF-8
            try:
                chunk.decode("utf-8")
                return False
            except UnicodeDecodeError:
                return True
    except Exception:
        return True


def scan_repository(repo_path: str) -> List[FileInfo]:
    """
    Scan a repository and return information about all source files.
    
    Args:
        repo_path: Path to the repository root
        
    Returns:
        List of FileInfo objects for each source file
    """
    repo = Path(repo_path).resolve()
    files: List[FileInfo] = []
    
    for root, dirs, filenames in os.walk(repo):
        # Filter out directories to skip (modifies dirs in-place)
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        
        for filename in filenames:
            file_path = Path(root) / filename
            
            # Check extension
            language = detect_language(file_path)
            if language is None:
                continue
            
            # Check file size
            try:
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            
            # Check if binary
            if is_binary_file(file_path):
                continue
            
            # Compute hash
            try:
                file_hash = compute_file_hash(file_path)
            except Exception:
                continue
            
            # Get relative path
            rel_path = str(file_path.relative_to(repo))
            
            files.append(FileInfo(
                file_path=rel_path,
                file_hash=file_hash,
                language=language,
            ))
    
    return files


def detect_moves(
    orphaned: Dict[str, str],  # path -> hash
    new_files: Dict[str, str],  # path -> hash
) -> List[Tuple[str, str]]:
    """
    Detect files that were moved/renamed by matching content hashes.
    
    Args:
        orphaned: Dict of paths in DB but not on disk, with their hashes
        new_files: Dict of paths on disk but not in DB, with their hashes
        
    Returns:
        List of (old_path, new_path) tuples for detected moves
    """
    moves: List[Tuple[str, str]] = []
    
    # Build reverse lookup: hash -> list of paths
    orphaned_by_hash: Dict[str, List[str]] = {}
    for path, hash_val in orphaned.items():
        orphaned_by_hash.setdefault(hash_val, []).append(path)
    
    new_by_hash: Dict[str, List[str]] = {}
    for path, hash_val in new_files.items():
        new_by_hash.setdefault(hash_val, []).append(path)
    
    # Find 1:1 matches
    for hash_val, orphaned_paths in orphaned_by_hash.items():
        if hash_val in new_by_hash:
            new_paths = new_by_hash[hash_val]
            # Only match if exactly one orphaned and one new path share this hash
            if len(orphaned_paths) == 1 and len(new_paths) == 1:
                moves.append((orphaned_paths[0], new_paths[0]))
    
    return moves
