"""Tests for benchmark config loader and serialization."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.config import load_config, serialize_config, validate_kiro_executable
from benchmark.models import AutomationConfig, BenchmarkConfig


class TestLoadConfig:
    """Tests for load_config()."""

    def _write_yaml(self, content: str) -> str:
        """Write YAML content to a temp file and return the path."""
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        return path

    def test_load_minimal_config(self):
        path = self._write_yaml('repo_path: "my_project"\n')
        try:
            config = load_config(path)
            assert config.repo_path == "my_project"
            assert config.prompt_file == "benchmark_output/session_script.json"
            assert config.output_dir == "benchmark_output"
            assert config.output_format == "json"
            assert config.proxy_port == 8080
            assert config.timeout_seconds == 120
        finally:
            os.unlink(path)

    def test_load_full_config(self):
        content = (
            'repo_path: "example_project"\n'
            'prompt_file: "custom/script.json"\n'
            'output_dir: "custom_output"\n'
            'output_format: "csv"\n'
            "proxy_port: 9090\n"
            "timeout_seconds: 60\n"
        )
        path = self._write_yaml(content)
        try:
            config = load_config(path)
            assert config.repo_path == "example_project"
            assert config.prompt_file == "custom/script.json"
            assert config.output_dir == "custom_output"
            assert config.output_format == "csv"
            assert config.proxy_port == 9090
            assert config.timeout_seconds == 60
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(SystemExit):
            load_config("/nonexistent/path/config.yaml")

    def test_missing_repo_path(self):
        path = self._write_yaml('output_dir: "out"\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_output_format(self):
        path = self._write_yaml('repo_path: "proj"\noutput_format: "xml"\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_proxy_port_negative(self):
        path = self._write_yaml('repo_path: "proj"\nproxy_port: -1\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_proxy_port_zero(self):
        path = self._write_yaml('repo_path: "proj"\nproxy_port: 0\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_proxy_port_string(self):
        path = self._write_yaml('repo_path: "proj"\nproxy_port: "abc"\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_timeout_seconds_negative(self):
        path = self._write_yaml('repo_path: "proj"\ntimeout_seconds: -10\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_timeout_seconds_zero(self):
        path = self._write_yaml('repo_path: "proj"\ntimeout_seconds: 0\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_timeout_seconds_string(self):
        path = self._write_yaml('repo_path: "proj"\ntimeout_seconds: "slow"\n')
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = self._write_yaml("")
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_null_repo_path(self):
        path = self._write_yaml("repo_path: null\n")
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_load_config_with_automation_section(self):
        content = (
            'repo_path: "proj"\n'
            "automation:\n"
            '  kiro_path: "/usr/bin/kiro"\n'
            "  idle_timeout: 45\n"
            "  turn_timeout: 600\n"
            "  startup_timeout: 90\n"
        )
        path = self._write_yaml(content)
        try:
            config = load_config(path)
            assert config.automation.kiro_path == "/usr/bin/kiro"
            assert config.automation.idle_timeout == 45
            assert config.automation.turn_timeout == 600
            assert config.automation.startup_timeout == 90
        finally:
            os.unlink(path)

    def test_load_config_without_automation_uses_defaults(self):
        path = self._write_yaml('repo_path: "proj"\n')
        try:
            config = load_config(path)
            assert config.automation.kiro_path == "kiro"
            assert config.automation.idle_timeout == 30
            assert config.automation.turn_timeout == 300
            assert config.automation.startup_timeout == 60
        finally:
            os.unlink(path)

    def test_invalid_automation_idle_timeout_negative(self):
        content = 'repo_path: "proj"\nautomation:\n  idle_timeout: -5\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_idle_timeout_zero(self):
        content = 'repo_path: "proj"\nautomation:\n  idle_timeout: 0\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_idle_timeout_string(self):
        content = 'repo_path: "proj"\nautomation:\n  idle_timeout: "slow"\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_turn_timeout_negative(self):
        content = 'repo_path: "proj"\nautomation:\n  turn_timeout: -1\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_startup_timeout_zero(self):
        content = 'repo_path: "proj"\nautomation:\n  startup_timeout: 0\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_kiro_path_empty(self):
        content = 'repo_path: "proj"\nautomation:\n  kiro_path: ""\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_kiro_path_whitespace(self):
        content = 'repo_path: "proj"\nautomation:\n  kiro_path: "   "\n'
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_invalid_automation_prefix_map_empty_value(self):
        content = (
            'repo_path: "proj"\n'
            "automation:\n"
            "  treatment_prefix_map:\n"
            '    task_description: ""\n'
        )
        path = self._write_yaml(content)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_valid_automation_prefix_map(self):
        content = (
            'repo_path: "proj"\n'
            "automation:\n"
            "  treatment_prefix_map:\n"
            '    task_description: "custom-plan"\n'
            '    implementation: "custom-fix"\n'
        )
        path = self._write_yaml(content)
        try:
            config = load_config(path)
            assert config.automation.treatment_prefix_map["task_description"] == "custom-plan"
            assert config.automation.treatment_prefix_map["implementation"] == "custom-fix"
        finally:
            os.unlink(path)


class TestSerializeConfig:
    """Tests for serialize_config()."""

    def test_serialize_produces_yaml(self):
        config = BenchmarkConfig(repo_path="my_project")
        yaml_str = serialize_config(config)
        assert "repo_path: my_project" in yaml_str
        assert "proxy_port: 8080" in yaml_str

    def test_serialize_custom_values(self):
        config = BenchmarkConfig(
            repo_path="proj",
            prompt_file="custom.json",
            output_dir="out",
            output_format="csv",
            proxy_port=9090,
            timeout_seconds=60,
        )
        yaml_str = serialize_config(config)
        assert "output_format: csv" in yaml_str
        assert "proxy_port: 9090" in yaml_str
        assert "timeout_seconds: 60" in yaml_str

    def test_serialize_includes_automation_section(self):
        from benchmark.models import AutomationConfig
        config = BenchmarkConfig(
            repo_path="proj",
            automation=AutomationConfig(
                kiro_path="/usr/bin/kiro",
                idle_timeout=45,
            ),
        )
        yaml_str = serialize_config(config)
        assert "automation:" in yaml_str
        assert "kiro_path: /usr/bin/kiro" in yaml_str
        assert "idle_timeout: 45" in yaml_str


class TestConfigRoundTrip:
    """Tests for config round-trip serialization."""

    def test_round_trip_default_config(self):
        original = BenchmarkConfig(repo_path="example_project")
        yaml_str = serialize_config(original)

        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(yaml_str)
            loaded = load_config(path)
            assert loaded == original
        finally:
            os.unlink(path)

    def test_round_trip_custom_config(self):
        original = BenchmarkConfig(
            repo_path="my_repo",
            prompt_file="scripts/prompts.json",
            output_dir="results",
            output_format="csv",
            proxy_port=9999,
            timeout_seconds=300,
        )
        yaml_str = serialize_config(original)

        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(yaml_str)
            loaded = load_config(path)
            assert loaded == original
        finally:
            os.unlink(path)

    def test_load_example_config_file(self):
        """Verify the example benchmark_config.yaml loads correctly."""
        config = load_config("benchmark_config.yaml")
        assert config.repo_path == "example_project"
        assert config.prompt_file == "benchmark_output/session_script.json"
        assert config.output_dir == "benchmark_output"
        assert config.output_format == "json"
        assert config.proxy_port == 8080
        assert config.timeout_seconds == 120


class TestValidateKiroExecutable:
    """Tests for validate_kiro_executable()."""

    def test_raises_system_exit_when_not_found(self):
        """Kiro executable not on PATH should raise SystemExit."""
        config = BenchmarkConfig(
            repo_path="proj",
            automation=AutomationConfig(kiro_path="nonexistent-kiro-binary-xyz"),
        )
        with pytest.raises(SystemExit):
            validate_kiro_executable(config)

    def test_passes_when_executable_found(self):
        """A known executable should not raise."""
        from unittest.mock import patch

        config = BenchmarkConfig(
            repo_path="proj",
            automation=AutomationConfig(kiro_path="kiro"),
        )
        with patch("benchmark.config.shutil.which", return_value="/usr/bin/kiro"):
            # Should not raise
            validate_kiro_executable(config)

    def test_error_message_includes_kiro_path(self, capsys):
        """Error message should mention the configured kiro_path."""
        config = BenchmarkConfig(
            repo_path="proj",
            automation=AutomationConfig(kiro_path="my-custom-kiro"),
        )
        with pytest.raises(SystemExit):
            validate_kiro_executable(config)
        captured = capsys.readouterr()
        assert "my-custom-kiro" in captured.out
        assert "not found on PATH" in captured.out


# ---------------------------------------------------------------------------
# 8.2  Property-based test: config YAML round-trip
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st, settings


config_strategy = st.builds(
    BenchmarkConfig,
    repo_path=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))),
    prompt_file=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))),
    output_dir=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))),
    output_format=st.sampled_from(["json", "csv"]),
    proxy_port=st.integers(min_value=1, max_value=65535),
    timeout_seconds=st.integers(min_value=1, max_value=3600),
)


class TestConfigRoundTripProperty:
    """**Validates: Requirements 7.5**"""

    @given(config=config_strategy)
    @settings(max_examples=50)
    def test_config_round_trip_property(self, config):
        """parse(serialize(c)) == c for arbitrary BenchmarkConfig instances."""
        yaml_str = serialize_config(config)
        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(yaml_str)
            loaded = load_config(path)
            assert loaded == config
        finally:
            os.unlink(path)
