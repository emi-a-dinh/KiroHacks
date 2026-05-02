"""Tests for the indexer models."""

import sys
from pathlib import Path

# Add context-lens/src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "context-lens" / "src"))

from indexer.models import FileInfo, CodeUnit, Edge, IndexResult


class TestFileInfo:
    """Tests for FileInfo dataclass."""

    def test_create_file_info(self):
        info = FileInfo(
            file_path="src/main.py",
            file_hash="abc123",
            language="python"
        )
        assert info.file_path == "src/main.py"
        assert info.file_hash == "abc123"
        assert info.language == "python"

    def test_file_info_optional_language(self):
        info = FileInfo(file_path="unknown.txt", file_hash="def456")
        assert info.language is None


class TestCodeUnit:
    """Tests for CodeUnit dataclass."""

    def test_create_function_unit(self):
        unit = CodeUnit(
            unit_id=1,
            file_path="src/utils.py",
            symbol_name="calculate",
            unit_type="function",
            parent_class=None,
            signature="def calculate(x: int, y: int) -> int",
            start_line=10,
            end_line=15,
            full_code="def calculate(x: int, y: int) -> int:\n    return x + y"
        )
        assert unit.symbol_name == "calculate"
        assert unit.unit_type == "function"
        assert unit.parent_class is None

    def test_create_method_unit(self):
        unit = CodeUnit(
            unit_id=2,
            file_path="src/models.py",
            symbol_name="process",
            unit_type="method",
            parent_class="DataProcessor",
            signature="def process(self, data: list) -> list",
            start_line=20,
            end_line=30,
            full_code="def process(self, data: list) -> list:\n    return [x * 2 for x in data]"
        )
        assert unit.unit_type == "method"
        assert unit.parent_class == "DataProcessor"


class TestEdge:
    """Tests for Edge dataclass."""

    def test_create_edge(self):
        edge = Edge(caller_id=1, callee_id=2)
        assert edge.caller_id == 1
        assert edge.callee_id == 2


class TestIndexResult:
    """Tests for IndexResult dataclass."""

    def test_default_values(self):
        result = IndexResult()
        assert result.files_scanned == 0
        assert result.units_extracted == 0
        assert result.index_path == ""

    def test_to_dict(self):
        result = IndexResult(
            files_scanned=10,
            files_updated=3,
            units_extracted=25,
            call_edges=15,
            index_path="/tmp/index.db",
            index_time_seconds=1.5
        )
        d = result.to_dict()
        assert d["files_scanned"] == 10
        assert d["files_updated"] == 3
        assert d["units_extracted"] == 25
        assert d["call_edges"] == 15
        assert d["index_path"] == "/tmp/index.db"
        assert d["index_time_seconds"] == 1.5
