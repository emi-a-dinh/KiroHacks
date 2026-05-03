"""Config loader for the AI IDE Token Benchmark.

Loads YAML configuration, validates required fields, applies defaults,
and supports round-trip serialization.
"""

import shutil

import yaml

from benchmark.models import BenchmarkConfig


def load_config(path: str) -> BenchmarkConfig:
    """Load and validate a BenchmarkConfig from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A validated BenchmarkConfig instance.

    Raises:
        SystemExit: If the file cannot be read, required fields are missing,
            or field values are invalid.
    """
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {path}")
        raise SystemExit(1)
    except Exception as e:
        print(f"Error: Could not read config file '{path}': {e}")
        raise SystemExit(1)

    if not isinstance(data, dict):
        print(f"Error: Config file '{path}' does not contain a valid YAML mapping.")
        raise SystemExit(1)

    if "repo_path" not in data or data["repo_path"] is None:
        print("Error: Required config parameter 'repo_path' is missing.")
        raise SystemExit(1)

    _validate_config(data)

    return BenchmarkConfig.from_dict(data)


def serialize_config(config: BenchmarkConfig) -> str:
    """Serialize a BenchmarkConfig to a YAML string.

    This enables the round-trip property:
        load_config(write(serialize_config(c))) == c

    Args:
        config: The BenchmarkConfig to serialize.

    Returns:
        A YAML string representation of the config.
    """
    return yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False)


def _validate_config(data: dict) -> None:
    """Validate config field values.

    Args:
        data: The raw config dictionary.

    Raises:
        SystemExit: If any field value is invalid.
    """
    output_format = data.get("output_format", "json")
    if output_format not in ("json", "csv"):
        print(
            f"Error: Invalid 'output_format' value '{output_format}'. "
            f"Must be 'json' or 'csv'."
        )
        raise SystemExit(1)

    proxy_port = data.get("proxy_port", 8080)
    if not isinstance(proxy_port, int) or proxy_port <= 0:
        print(
            f"Error: Invalid 'proxy_port' value '{proxy_port}'. "
            f"Must be a positive integer."
        )
        raise SystemExit(1)

    timeout_seconds = data.get("timeout_seconds", 120)
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        print(
            f"Error: Invalid 'timeout_seconds' value '{timeout_seconds}'. "
            f"Must be a positive integer."
        )
        raise SystemExit(1)

    # Validate optional automation section
    automation = data.get("automation")
    if automation is not None:
        if not isinstance(automation, dict):
            print(
                f"Error: Invalid 'automation' section. Must be a YAML mapping."
            )
            raise SystemExit(1)

        kiro_path = automation.get("kiro_path")
        if kiro_path is not None:
            if not isinstance(kiro_path, str) or not kiro_path.strip():
                print(
                    f"Error: Invalid 'automation.kiro_path' value '{kiro_path}'. "
                    f"Must be a non-empty string."
                )
                raise SystemExit(1)

        for timeout_field in ("idle_timeout", "turn_timeout", "startup_timeout"):
            value = automation.get(timeout_field)
            if value is not None:
                if not isinstance(value, int) or value <= 0:
                    print(
                        f"Error: Invalid 'automation.{timeout_field}' value '{value}'. "
                        f"Must be a positive integer."
                    )
                    raise SystemExit(1)

        prefix_map = automation.get("treatment_prefix_map")
        if prefix_map is not None:
            if not isinstance(prefix_map, dict):
                print(
                    f"Error: Invalid 'automation.treatment_prefix_map'. "
                    f"Must be a YAML mapping."
                )
                raise SystemExit(1)
            for role, prefix in prefix_map.items():
                if not isinstance(prefix, str) or not prefix.strip():
                    print(
                        f"Error: Invalid treatment_prefix_map value for role '{role}'. "
                        f"Must be a non-empty string."
                    )
                    raise SystemExit(1)


def validate_kiro_executable(config: BenchmarkConfig) -> None:
    """Validate that the configured Kiro executable can be found on PATH.

    This check is intended to be called from the CLI before starting the proxy,
    not during config loading. This avoids breaking tests that load configs
    in environments where Kiro is not installed.

    Args:
        config: A validated BenchmarkConfig instance.

    Raises:
        SystemExit: If the Kiro executable is not found on PATH.
    """
    kiro_path = config.automation.kiro_path
    if shutil.which(kiro_path) is None:
        print(
            f"Error: Kiro executable '{kiro_path}' not found on PATH. "
            f"Set 'automation.kiro_path' in the config file."
        )
        raise SystemExit(1)
