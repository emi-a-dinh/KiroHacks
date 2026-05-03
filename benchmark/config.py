"""Config loader for the AI IDE Token Benchmark.

Loads YAML configuration, validates required fields, applies defaults,
and supports round-trip serialization.
"""

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
