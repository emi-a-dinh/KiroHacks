"""Tests for benchmark config loader and serialization."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.config import load_config, serialize_config
from benchmark.models import BenchmarkConfig


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
