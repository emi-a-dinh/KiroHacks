"""Data models for the indexer."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileInfo:
    """Information about a source file."""
    file_path: str
    file_hash: str
    language: Optional[str] = None


@dataclass
class CodeUnit:
    """A code unit (function, class, method, or constant)."""
    unit_id: Optional[int]  # None until inserted into DB
    file_path: str
    symbol_name: str
    unit_type: str  # 'function', 'class', 'method', 'constant'
    parent_class: Optional[str]  # Only for methods
    signature: str  # Compact one-liner
    start_line: int
    end_line: int
    full_code: str


@dataclass
class Edge:
    """A call edge between two units."""
    caller_id: int
    callee_id: int


@dataclass
class IndexResult:
    """Result of an indexing operation."""
    files_scanned: int = 0
    files_skipped: int = 0
    files_moved: int = 0
    files_updated: int = 0
    files_deleted: int = 0
    units_extracted: int = 0
    call_edges: int = 0
    index_path: str = ""
    index_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "files_scanned": self.files_scanned,
            "files_skipped": self.files_skipped,
            "files_moved": self.files_moved,
            "files_updated": self.files_updated,
            "files_deleted": self.files_deleted,
            "units_extracted": self.units_extracted,
            "call_edges": self.call_edges,
            "index_path": self.index_path,
            "index_time_seconds": self.index_time_seconds,
        }
