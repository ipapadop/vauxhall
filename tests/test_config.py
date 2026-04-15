"""Tests for the configuration module."""

from pathlib import Path

import yaml

from vauxhall.config import Config


def test_config_load_defaults(tmp_path: Path) -> None:
    """Verify that Config.load uses defaults when file is missing."""
    # Ensure file doesn't exist
    non_existent = tmp_path / "missing.yaml"
    cfg = Config.load(non_existent)

    assert cfg.mqtt.host == "localhost"
    assert cfg.mqtt.port == 1883
    assert cfg.dashboard.stale_threshold == 120


def test_config_load_from_yaml(tmp_path: Path) -> None:
    """Verify that Config.load correctly parses a YAML file."""
    config_file = tmp_path / "vauxhall.yaml"
    data = {
        "mqtt": {"host": "test_mqtt", "port": 9999},
        "dashboard": {"stale_threshold": 300},
        "logging": {"level": "DEBUG"},
    }
    with open(config_file, "w") as f:
        yaml.dump(data, f)

    cfg = Config.load(config_file)

    assert cfg.mqtt.host == "test_mqtt"
    assert cfg.mqtt.port == 9999
    assert cfg.dashboard.stale_threshold == 300
    assert cfg.logging.level == "DEBUG"


def test_config_partial_load(tmp_path: Path) -> None:
    """Verify that Config.load handles partial YAML files."""
    config_file = tmp_path / "partial.yaml"
    data = {"mqtt": {"host": "only_host"}}
    with open(config_file, "w") as f:
        yaml.dump(data, f)

    cfg = Config.load(config_file)

    assert cfg.mqtt.host == "only_host"
    assert cfg.mqtt.port == 1883  # Default
    assert cfg.dashboard.stale_threshold == 120  # Default
