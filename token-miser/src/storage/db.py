"""SQLite database operations for the index."""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from indexer.models import CodeUnit, Edge, FileInfo


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    file_path    TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,
    language     TEXT,
    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS units (
    unit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path    TEXT NOT NULL REFERENCES files(file_path) ON DELETE CASCADE,
    symbol_name  TEXT NOT NULL,
    unit_type    TEXT NOT NULL,
    parent_class TEXT,
    signature    TEXT NOT NULL,
    start_line   INTEGER NOT NULL,
    end_line     INTEGER NOT NULL,
    full_code    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    caller_id    INTEGER NOT NULL REFERENCES units(unit_id) ON DELETE CASCADE,
    callee_id    INTEGER NOT NULL REFERENCES units(unit_id) ON DELETE CASCADE,
    PRIMARY KEY (caller_id, callee_id)
);

CREATE INDEX IF NOT EXISTS idx_units_file ON units(file_path);
CREATE INDEX IF NOT EXISTS idx_units_symbol ON units(symbol_name);
CREATE INDEX IF NOT EXISTS idx_edges_caller ON edges(caller_id);
CREATE INDEX IF NOT EXISTS idx_edges_callee ON edges(callee_id);
"""


class Database:
    """SQLite database for storing the code index."""
    
    def __init__(self, db_path: str):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        
        # Create schema
        self.conn.executescript(SCHEMA)
        self.conn.commit()
    
    def close(self):
        """Close the database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # File operations
    
    def get_all_files(self) -> Dict[str, str]:
        """Get all indexed files with their hashes."""
        cursor = self.conn.execute("SELECT file_path, file_hash FROM files")
        return {row["file_path"]: row["file_hash"] for row in cursor}
    
    def get_file(self, file_path: str) -> Optional[FileInfo]:
        """Get a file by path."""
        cursor = self.conn.execute(
            "SELECT file_path, file_hash, language FROM files WHERE file_path = ?",
            (file_path,)
        )
        row = cursor.fetchone()
        if row:
            return FileInfo(
                file_path=row["file_path"],
                file_hash=row["file_hash"],
                language=row["language"],
            )
        return None
    
    def upsert_file(self, file_info: FileInfo):
        """Insert or update a file."""
        self.conn.execute(
            """
            INSERT INTO files (file_path, file_hash, language, last_indexed)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                language = excluded.language,
                last_indexed = CURRENT_TIMESTAMP
            """,
            (file_info.file_path, file_info.file_hash, file_info.language)
        )
    
    def delete_file(self, file_path: str):
        """Delete a file and its units (cascade)."""
        self.conn.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
    
    def update_file_path(self, old_path: str, new_path: str):
        """Update a file's path (for move detection)."""
        self.conn.execute(
            "UPDATE files SET file_path = ? WHERE file_path = ?",
            (new_path, old_path)
        )
        self.conn.execute(
            "UPDATE units SET file_path = ? WHERE file_path = ?",
            (new_path, old_path)
        )
    
    # Unit operations
    
    def get_units_for_file(self, file_path: str) -> List[CodeUnit]:
        """Get all units for a file."""
        cursor = self.conn.execute(
            """
            SELECT unit_id, file_path, symbol_name, unit_type, parent_class,
                   signature, start_line, end_line, full_code
            FROM units WHERE file_path = ?
            """,
            (file_path,)
        )
        return [
            CodeUnit(
                unit_id=row["unit_id"],
                file_path=row["file_path"],
                symbol_name=row["symbol_name"],
                unit_type=row["unit_type"],
                parent_class=row["parent_class"],
                signature=row["signature"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                full_code=row["full_code"],
            )
            for row in cursor
        ]
    
    def get_all_units(self) -> List[CodeUnit]:
        """Get all units in the database."""
        cursor = self.conn.execute(
            """
            SELECT unit_id, file_path, symbol_name, unit_type, parent_class,
                   signature, start_line, end_line, full_code
            FROM units ORDER BY file_path, start_line
            """
        )
        return [
            CodeUnit(
                unit_id=row["unit_id"],
                file_path=row["file_path"],
                symbol_name=row["symbol_name"],
                unit_type=row["unit_type"],
                parent_class=row["parent_class"],
                signature=row["signature"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                full_code=row["full_code"],
            )
            for row in cursor
        ]
    
    def get_units_by_ids(self, unit_ids: List[int]) -> List[CodeUnit]:
        """Get units by their IDs."""
        if not unit_ids:
            return []
        
        placeholders = ",".join("?" * len(unit_ids))
        cursor = self.conn.execute(
            f"""
            SELECT unit_id, file_path, symbol_name, unit_type, parent_class,
                   signature, start_line, end_line, full_code
            FROM units WHERE unit_id IN ({placeholders})
            """,
            unit_ids
        )
        return [
            CodeUnit(
                unit_id=row["unit_id"],
                file_path=row["file_path"],
                symbol_name=row["symbol_name"],
                unit_type=row["unit_type"],
                parent_class=row["parent_class"],
                signature=row["signature"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                full_code=row["full_code"],
            )
            for row in cursor
        ]
    
    def insert_unit(self, unit: CodeUnit) -> int:
        """Insert a unit and return its ID."""
        cursor = self.conn.execute(
            """
            INSERT INTO units (file_path, symbol_name, unit_type, parent_class,
                              signature, start_line, end_line, full_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit.file_path,
                unit.symbol_name,
                unit.unit_type,
                unit.parent_class,
                unit.signature,
                unit.start_line,
                unit.end_line,
                unit.full_code,
            )
        )
        return cursor.lastrowid
    
    def delete_units_for_file(self, file_path: str):
        """Delete all units for a file."""
        self.conn.execute("DELETE FROM units WHERE file_path = ?", (file_path,))
    
    def get_unit_count(self) -> int:
        """Get total number of units."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM units")
        return cursor.fetchone()[0]
    
    # Edge operations
    
    def clear_edges(self):
        """Delete all edges."""
        self.conn.execute("DELETE FROM edges")
    
    def insert_edges(self, edges: List[Edge]):
        """Insert multiple edges."""
        self.conn.executemany(
            "INSERT OR IGNORE INTO edges (caller_id, callee_id) VALUES (?, ?)",
            [(e.caller_id, e.callee_id) for e in edges]
        )
    
    def get_all_edges(self) -> List[Edge]:
        """Get all edges."""
        cursor = self.conn.execute("SELECT caller_id, callee_id FROM edges")
        return [Edge(caller_id=row["caller_id"], callee_id=row["callee_id"]) for row in cursor]
    
    def get_edges_for_units(self, unit_ids: List[int]) -> Tuple[Dict[int, List[int]], Dict[int, List[int]]]:
        """
        Get edges for a set of units.
        
        Returns:
            Tuple of (calls, called_by) dicts mapping unit_id -> list of related unit_ids
        """
        if not unit_ids:
            return {}, {}
        
        calls: Dict[int, List[int]] = {uid: [] for uid in unit_ids}
        called_by: Dict[int, List[int]] = {uid: [] for uid in unit_ids}
        
        placeholders = ",".join("?" * len(unit_ids))
        
        # Get outgoing edges (what these units call)
        cursor = self.conn.execute(
            f"SELECT caller_id, callee_id FROM edges WHERE caller_id IN ({placeholders})",
            unit_ids
        )
        for row in cursor:
            calls[row["caller_id"]].append(row["callee_id"])
        
        # Get incoming edges (what calls these units)
        cursor = self.conn.execute(
            f"SELECT caller_id, callee_id FROM edges WHERE callee_id IN ({placeholders})",
            unit_ids
        )
        for row in cursor:
            called_by[row["callee_id"]].append(row["caller_id"])
        
        return calls, called_by
    
    def get_edge_count(self) -> int:
        """Get total number of edges."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM edges")
        return cursor.fetchone()[0]
    
    def get_neighbors(self, unit_ids: List[int]) -> List[int]:
        """Get all direct neighbors (callers and callees) of the given units."""
        if not unit_ids:
            return []
        
        placeholders = ",".join("?" * len(unit_ids))
        
        # Get callees
        cursor = self.conn.execute(
            f"SELECT DISTINCT callee_id FROM edges WHERE caller_id IN ({placeholders})",
            unit_ids
        )
        neighbors = {row["callee_id"] for row in cursor}
        
        # Get callers
        cursor = self.conn.execute(
            f"SELECT DISTINCT caller_id FROM edges WHERE callee_id IN ({placeholders})",
            unit_ids
        )
        neighbors.update(row["caller_id"] for row in cursor)
        
        # Remove the original units
        neighbors -= set(unit_ids)
        
        return list(neighbors)
    
    # Transaction helpers
    
    def commit(self):
        """Commit the current transaction."""
        self.conn.commit()
    
    def rollback(self):
        """Rollback the current transaction."""
        self.conn.rollback()
