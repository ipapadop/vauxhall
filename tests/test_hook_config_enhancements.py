# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for enhanced hook configuration."""

import os
from pathlib import Path
from unittest.mock import patch

from vauxhall.hooks.config import HookConfig


def test_hook_config_load_env_only() -> None:
    """Test environment-only optimization in HookConfig.load()."""
    env = {
        "VAUXHALL_MQTT_HOST": "env-host",
        "VAUXHALL_MQTT_PORT": "1884",
        "VAUXHALL_MQTT_KEEPALIVE": "120",
        "VAUXHALL_LOGGING_LEVEL": "DEBUG",
    }
    # Should not try to find or load file when VAUXHALL_MQTT_HOST is set
    # and no path provided
    with (
        patch.dict(os.environ, env),
        patch("vauxhall.core.config.find_config_file") as mock_find,
    ):
        config = HookConfig.load()
        mock_find.assert_not_called()
        assert config.mqtt.host == "env-host"
        assert config.mqtt.port == 1884
        assert config.mqtt.keepalive == 120
        assert config.logging.level == "DEBUG"


def test_hook_config_load_search_path(tmp_path: Path) -> None:
    """Test search path resolution in HookConfig.load()."""
    config_file = tmp_path / "vauxhall_hooks.json"
    config_file.write_text('{"mqtt": {"host": "path-host"}}', encoding="utf-8")

    with patch("vauxhall.core.config.find_config_file", return_value=config_file):
        config = HookConfig.load()
        assert config.mqtt.host == "path-host"


def test_hook_config_load_env_override(tmp_path: Path) -> None:
    """Test that environment variables override file values."""
    config_file = tmp_path / "vauxhall_hooks.json"
    config_file.write_text('{"mqtt": {"host": "file-host"}}', encoding="utf-8")

    with patch.dict(os.environ, {"VAUXHALL_MQTT_HOST": "env-host"}):
        config = HookConfig.load(config_file)
        assert config.mqtt.host == "env-host"
