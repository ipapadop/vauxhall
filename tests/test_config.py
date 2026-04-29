# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the configuration module."""

import json
from pathlib import Path

from vauxhall.core.config import Config


def test_config_load_defaults(tmp_path: Path) -> None:
    """Verify that Config.load uses defaults when file is missing."""
    # Ensure file doesn't exist
    non_existent = tmp_path / "missing.json"
    cfg = Config.load(non_existent)

    assert cfg.mqtt.host == "localhost"
    assert cfg.mqtt.port == 1883
    assert cfg.dashboard.stale_threshold == 120


def test_config_load_from_json(tmp_path: Path) -> None:
    """Verify that Config.load correctly parses a JSON file."""
    config_file = tmp_path / "vauxhall.json"
    data = {
        "mqtt": {"host": "test_mqtt", "port": 9999},
        "dashboard": {"stale_threshold": 300},
        "logging": {"level": "DEBUG"},
    }
    with config_file.open("w") as f:
        json.dump(data, f)

    cfg = Config.load(config_file)

    assert cfg.mqtt.host == "test_mqtt"
    assert cfg.mqtt.port == 9999
    assert cfg.dashboard.stale_threshold == 300
    assert cfg.logging.level == "DEBUG"


def test_config_partial_load(tmp_path: Path) -> None:
    """Verify that Config.load handles partial JSON files."""
    config_file = tmp_path / "partial.json"
    data = {"mqtt": {"host": "only_host"}}
    with config_file.open("w") as f:
        json.dump(data, f)

    cfg = Config.load(config_file)

    assert cfg.mqtt.host == "only_host"
    assert cfg.mqtt.port == 1883  # Default
    assert cfg.dashboard.stale_threshold == 120  # Default


def test_config_save(tmp_path: Path) -> None:
    """Verify that Config.save correctly writes a JSON file."""
    config_file = tmp_path / "save_test.json"
    cfg = Config()
    cfg.mqtt.host = "saved_host"
    cfg.save(config_file)

    assert config_file.exists()
    with config_file.open() as f:
        data = json.load(f)

    assert data["mqtt"]["host"] == "saved_host"
