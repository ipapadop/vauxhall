# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Unit tests for ConfigResolver."""

import os
from pathlib import Path
from unittest.mock import patch

from vauxhall.core.config import ConfigResolver


def test_config_resolver_tiered_resolution() -> None:
    """Test that ConfigResolver resolves settings in the correct order."""
    # Arrange
    json_data = {"mqtt": {"host": "mqtt.example.com", "port": 1883}}

    # 1. Default
    resolver_default = ConfigResolver("test_config.json")
    assert (
        resolver_default.get("VAUXHALL_MQTT_HOST", "mqtt", "host", "localhost")
        == "localhost"
    )

    # 2. JSON (mocking load_config_data and find_config_file)
    resolver_json = ConfigResolver("test_config.json")
    with (
        patch("vauxhall.core.config.find_config_file", return_value=Path("dummy.json")),
        patch("vauxhall.core.config.load_config_data", return_value=json_data),
    ):
        assert (
            resolver_json.get("VAUXHALL_MQTT_HOST", "mqtt", "host", "localhost")
            == "mqtt.example.com"
        )
        assert resolver_json.get("VAUXHALL_MQTT_PORT", "mqtt", "port", 1883) == 1883

    # 3. Env
    resolver_env = ConfigResolver("test_config.json")
    with patch.dict(os.environ, {"VAUXHALL_MQTT_HOST": "env.host.com"}):
        assert (
            resolver_env.get("VAUXHALL_MQTT_HOST", "mqtt", "host", "localhost")
            == "env.host.com"
        )


def test_config_resolver_lazy_loading() -> None:
    """Test that ConfigResolver only loads JSON data when necessary."""
    # Arrange
    resolver = ConfigResolver("test_config.json")

    with patch("vauxhall.core.config.load_config_data") as mock_load:
        # Act: Access via Env var only
        with patch.dict(os.environ, {"VAUXHALL_MQTT_HOST": "env.host.com"}):
            value = resolver.get("VAUXHALL_MQTT_HOST", "mqtt", "host", "localhost")

        # Assert
        assert value == "env.host.com"
        mock_load.assert_not_called()

        # Act: Access something not in Env, should trigger load
        with patch(
            "vauxhall.core.config.find_config_file", return_value=Path("dummy.json")
        ):
            mock_load.return_value = {"mqtt": {"port": 1234}}
            value = resolver.get("VAUXHALL_MQTT_PORT", "mqtt", "port", 1883)

        # Assert
        assert value == 1234
        mock_load.assert_called_once()


def test_config_resolver_casting() -> None:
    """Test that ConfigResolver correctly casts environment variables."""
    resolver = ConfigResolver("test_config.json")

    # Int casting
    with patch.dict(os.environ, {"VAUXHALL_MQTT_PORT": "1234"}):
        assert resolver.get("VAUXHALL_MQTT_PORT", "mqtt", "port", 1883) == 1234

    # Bool casting
    with patch.dict(os.environ, {"VAUXHALL_DEBUG": "true"}):
        assert resolver.get("VAUXHALL_DEBUG", "core", "debug", False) is True
    with patch.dict(os.environ, {"VAUXHALL_DEBUG": "1"}):
        assert resolver.get("VAUXHALL_DEBUG", "core", "debug", False) is True
    with patch.dict(os.environ, {"VAUXHALL_DEBUG": "0"}):
        assert resolver.get("VAUXHALL_DEBUG", "core", "debug", True) is False
