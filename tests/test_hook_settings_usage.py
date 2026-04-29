# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests to ensure hooks use hook-specific settings."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from vauxhall.hooks.client import TelemetryClient
from vauxhall.hooks.config import HookConfig

def test_telemetry_client_uses_hook_settings(tmp_path):
    """Verify TelemetryClient picks up defaults from hook_settings."""
    config_file = tmp_path / "vauxhall_hooks.json"
    data = {
        "mqtt": {
            "host": "hook_host",
            "port": 9999,
            "keepalive": 120
        }
    }
    with config_file.open("w") as f:
        json.dump(data, f)
    
    # Load a specific config instance
    custom_settings = HookConfig.load(config_file)
    
    with patch("vauxhall.hooks.client.settings", custom_settings):
        with patch("vauxhall.hooks.client.mqtt.Client") as mock_mqtt:
            mock_inst = mock_mqtt.return_value
            client = TelemetryClient()
            assert client.host == "hook_host"
            assert client.port == 9999
            
            with client:
                mock_inst.connect.assert_called_once_with("hook_host", 9999, keepalive=120)
