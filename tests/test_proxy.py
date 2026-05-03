"""Tests for benchmark proxy module."""

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.proxy import ProxyManager, print_proxy_instructions


class TestAddonTemplate:
    """Tests for the _addon_template.py file."""

    def test_addon_template_exists(self):
        """The addon template file must exist in the benchmark package."""
        template_path = Path(__file__).parent.parent / "benchmark" / "_addon_template.py"
        assert template_path.exists(), f"Addon template not found at {template_path}"

    def test_addon_template_is_valid_python(self):
        """The addon template must be valid, parseable Python."""
        template_path = Path(__file__).parent.parent / "benchmark" / "_addon_template.py"
        source = template_path.read_text()
        # ast.parse will raise SyntaxError if the file is not valid Python
        tree = ast.parse(source, filename=str(template_path))
        assert tree is not None

    def test_addon_template_defines_addons_list(self):
        """The addon template must define a module-level 'addons' list."""
        template_path = Path(__file__).parent.parent / "benchmark" / "_addon_template.py"
        source = template_path.read_text()
        tree = ast.parse(source)

        # Look for a top-level assignment to 'addons'
        found = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "addons":
                        found = True
        assert found, "Addon template must define a module-level 'addons' variable"

    def test_addon_template_defines_usage_capture_addon_class(self):
        """The addon template must define the UsageCaptureAddon class."""
        template_path = Path(__file__).parent.parent / "benchmark" / "_addon_template.py"
        source = template_path.read_text()
        tree = ast.parse(source)

        class_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]
        assert "UsageCaptureAddon" in class_names

    def test_addon_template_has_response_method(self):
        """UsageCaptureAddon must have a response() method."""
        template_path = Path(__file__).parent.parent / "benchmark" / "_addon_template.py"
        source = template_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "UsageCaptureAddon":
                method_names = [
                    n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                assert "response" in method_names, "UsageCaptureAddon must have a response() method"
                return
        pytest.fail("UsageCaptureAddon class not found")

    def test_addon_template_has_request_method(self):
        """UsageCaptureAddon must have a request() method for MCP tool detection."""
        template_path = Path(__file__).parent.parent / "benchmark" / "_addon_template.py"
        source = template_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "UsageCaptureAddon":
                method_names = [
                    n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                assert "request" in method_names, "UsageCaptureAddon must have a request() method"
                return
        pytest.fail("UsageCaptureAddon class not found")


class TestReadEntries:
    """Tests for ProxyManager.read_entries()."""

    def test_read_entries_empty_file(self):
        """read_entries returns empty list for an empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)
            entries = pm.read_entries()
            assert entries == []
        finally:
            os.unlink(path)

    def test_read_entries_nonexistent_file(self):
        """read_entries returns empty list when the file doesn't exist."""
        pm = ProxyManager(port=8080, jsonl_path="/tmp/nonexistent_benchmark_test.jsonl")
        entries = pm.read_entries()
        assert entries == []

    def test_read_entries_parses_jsonl(self):
        """read_entries correctly parses multiple JSONL lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "token_usage", "input_tokens": 100, "output_tokens": 50, "timestamp": 1.0}) + "\n")
            f.write(json.dumps({"type": "token_usage", "input_tokens": 200, "output_tokens": 75, "timestamp": 2.0}) + "\n")
            f.write(json.dumps({"type": "mcp_tool_call", "tools": ["context_query"], "timestamp": 3.0}) + "\n")
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)
            entries = pm.read_entries()
            assert len(entries) == 3
            assert entries[0]["type"] == "token_usage"
            assert entries[0]["input_tokens"] == 100
            assert entries[1]["output_tokens"] == 75
            assert entries[2]["type"] == "mcp_tool_call"
            assert entries[2]["tools"] == ["context_query"]
        finally:
            os.unlink(path)

    def test_read_entries_skips_malformed_lines(self):
        """read_entries silently skips lines that aren't valid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "token_usage", "input_tokens": 10, "output_tokens": 5, "timestamp": 1.0}) + "\n")
            f.write("this is not json\n")
            f.write(json.dumps({"type": "warning", "message": "test", "timestamp": 2.0}) + "\n")
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)
            entries = pm.read_entries()
            assert len(entries) == 2
            assert entries[0]["type"] == "token_usage"
            assert entries[1]["type"] == "warning"
        finally:
            os.unlink(path)

    def test_read_entries_skips_blank_lines(self):
        """read_entries skips blank lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "token_usage", "input_tokens": 1, "output_tokens": 1, "timestamp": 1.0}) + "\n")
            f.write("\n")
            f.write("   \n")
            f.write(json.dumps({"type": "token_usage", "input_tokens": 2, "output_tokens": 2, "timestamp": 2.0}) + "\n")
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)
            entries = pm.read_entries()
            assert len(entries) == 2
        finally:
            os.unlink(path)


class TestReadNewEntries:
    """Tests for ProxyManager.read_new_entries()."""

    def test_read_new_entries_from_start(self):
        """read_new_entries from position 0 reads all entries."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "token_usage", "input_tokens": 10, "output_tokens": 5, "timestamp": 1.0}) + "\n")
            f.write(json.dumps({"type": "token_usage", "input_tokens": 20, "output_tokens": 10, "timestamp": 2.0}) + "\n")
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)
            entries, pos = pm.read_new_entries(0)
            assert len(entries) == 2
            assert pos > 0
        finally:
            os.unlink(path)

    def test_read_new_entries_tracks_position(self):
        """read_new_entries only returns entries after last_position."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "token_usage", "input_tokens": 10, "output_tokens": 5, "timestamp": 1.0}) + "\n")
            f.write(json.dumps({"type": "token_usage", "input_tokens": 20, "output_tokens": 10, "timestamp": 2.0}) + "\n")
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)

            # Read all entries first
            entries1, pos1 = pm.read_new_entries(0)
            assert len(entries1) == 2

            # No new entries at current position
            entries2, pos2 = pm.read_new_entries(pos1)
            assert len(entries2) == 0
            assert pos2 == pos1

            # Append a new entry
            with open(path, "a") as f:
                f.write(json.dumps({"type": "token_usage", "input_tokens": 30, "output_tokens": 15, "timestamp": 3.0}) + "\n")

            # Read only the new entry
            entries3, pos3 = pm.read_new_entries(pos2)
            assert len(entries3) == 1
            assert entries3[0]["input_tokens"] == 30
            assert pos3 > pos2
        finally:
            os.unlink(path)

    def test_read_new_entries_nonexistent_file(self):
        """read_new_entries returns empty list and same position for missing file."""
        pm = ProxyManager(port=8080, jsonl_path="/tmp/nonexistent_benchmark_test.jsonl")
        entries, pos = pm.read_new_entries(0)
        assert entries == []
        assert pos == 0

    def test_read_new_entries_with_warning_entries(self):
        """read_new_entries correctly parses warning-type entries."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "warning", "message": "No usage field in response", "timestamp": 1.0}) + "\n")
            path = f.name

        try:
            pm = ProxyManager(port=8080, jsonl_path=path)
            entries, pos = pm.read_new_entries(0)
            assert len(entries) == 1
            assert entries[0]["type"] == "warning"
            assert entries[0]["message"] == "No usage field in response"
        finally:
            os.unlink(path)


class TestPrintProxyInstructions:
    """Tests for print_proxy_instructions()."""

    def test_print_proxy_instructions_runs_without_error(self, capsys):
        """print_proxy_instructions should execute without raising."""
        print_proxy_instructions(8080)
        captured = capsys.readouterr()
        # The output goes through rich Console, so just verify no exception

    def test_print_proxy_instructions_custom_port(self, capsys):
        """print_proxy_instructions should use the provided port number."""
        # Just verify it doesn't crash with a custom port
        print_proxy_instructions(9999)
