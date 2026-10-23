# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for loading hook configuration."""

import os
from dataclasses import asdict
from unittest.mock import patch

from vauxhall.core.config import MQTTConfig
from vauxhall.hooks.config import HookConfig


def test_hook_config_load_env_only() -> None:
    """When the environment sets every field, no configuration file is looked up."""
    env = {
        f"VAUXHALL_MQTT_{name.upper()}": str(value)
        for name, value in asdict(MQTTConfig()).items()
    } | {
        "VAUXHALL_MQTT_HOST": "env-host",
        "VAUXHALL_MQTT_PORT": "1884",
        "VAUXHALL_MQTT_KEEPALIVE": "120",
        "VAUXHALL_LOGGING_LEVEL": "DEBUG",
    }
    # Should not try to find or load a file when the environment sets every
    # field and no path is provided
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
