# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for environment-variable overrides in dashboard configuration."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from vauxhall.dashboard.config import DashboardConfig


def test_dashboard_env_only_optimization() -> None:
    """Test that setting VAUXHALL_MQTT_HOST bypasses file loading."""
    env = {
        "VAUXHALL_MQTT_HOST": "env-mqtt-host",
        "VAUXHALL_DASHBOARD_PORT": "9090",
    }
    with patch.dict(os.environ, env):
        config = DashboardConfig.load()
        assert config.mqtt.host == "env-mqtt-host"
        assert config.dashboard.port == 9090


def test_dashboard_env_overrides_file(tmp_path: Path) -> None:
    """Test that environment variables override file values.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_file = tmp_path / "vauxhall_dashboard.json"
    config_file.write_text(json.dumps({"dashboard": {"port": 1111}}))

    env = {
        "VAUXHALL_DASHBOARD_PORT": "2222",
    }
    with patch.dict(os.environ, env):
        config = DashboardConfig.load(config_file)
        assert config.dashboard.port == 2222  # From env (overrides file)


def test_dashboard_find_config_in_cwd(tmp_path: Path) -> None:
    """Test finding config in current working directory.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_data = {"dashboard": {"window_title": "CWD Dashboard"}}

    # We need to change CWD or mock find_config_file.
    # Since we are testing find_config_file integration, let's mock the search paths
    # or Path.cwd()

    with patch("vauxhall.core.config.Path.cwd") as mock_cwd:
        mock_cwd.return_value = tmp_path
        config_file = tmp_path / "vauxhall_dashboard.json"
        config_file.write_text(json.dumps(config_data))

        # Ensure VAUXHALL_MQTT_HOST is NOT set to avoid optimization
        with patch.dict(os.environ, {}, clear=True):
            config = DashboardConfig.load()
            assert config.dashboard.window_title == "CWD Dashboard"


def test_dashboard_find_config_in_home(tmp_path: Path) -> None:
    """Test finding config in ~/.config/vauxhall/.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_data = {"dashboard": {"window_title": "Home Dashboard"}}
    home_config_dir = tmp_path / ".config" / "vauxhall"
    home_config_dir.mkdir(parents=True)
    config_file = home_config_dir / "vauxhall_dashboard.json"
    config_file.write_text(json.dumps(config_data))

    with patch("vauxhall.core.config.Path.home") as mock_home:
        mock_home.return_value = tmp_path
        # Also mock cwd to somewhere empty
        with patch("vauxhall.core.config.Path.cwd") as mock_cwd:
            mock_cwd.return_value = tmp_path / "empty"
            (tmp_path / "empty").mkdir()

            with patch.dict(os.environ, {}, clear=True):
                config = DashboardConfig.load()
                assert config.dashboard.window_title == "Home Dashboard"
