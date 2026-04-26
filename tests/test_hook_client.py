# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry hook client."""

import json
from unittest.mock import MagicMock, patch

from vauxhall.hooks.client import TelemetryClient, format_message


def test_format_message() -> None:
    """Test that message formatting returns a valid JSON with expected fields."""
    msg = format_message("Gemini", "/home/user/project", "Acting", tool="grep")
    data = json.loads(msg)
    assert data["agent"] == "Gemini"
    assert data["workspace"] == "/home/user/project"
    assert data["state"] == "Acting"
    assert data["details"]["tool"] == "grep"


def test_telemetry_client_fail_silently() -> None:
    """Test that TelemetryClient.send fails silently when broker is unreachable."""
    client = TelemetryClient(host="nonexistent.local", port=1883)
    # This should not raise an exception
    client.send("Gemini", "/home/user/project", "Acting", tool="grep")


@patch("vauxhall.hooks.client.mqtt.Client")
def test_telemetry_client_send_calls(mock_client_class: MagicMock) -> None:
    """Test that TelemetryClient.send calls all expected methods."""
    mock_client = mock_client_class.return_value
    mock_publish_result = MagicMock()
    mock_client.publish.return_value = mock_publish_result

    client = TelemetryClient(host="test_host", port=1234)
    client.send("Gemini", "/home/user/project", "Acting", env="local", tool="grep")

    mock_client.connect.assert_called_once_with("test_host", 1234, keepalive=60)
    mock_client.publish.assert_called_once()
    mock_publish_result.wait_for_publish.assert_called_once()
    mock_client.disconnect.assert_called_once()


def test_telemetry_client_context_manager() -> None:
    """Verify the context manager establishes a persistent connection."""
    with patch("vauxhall.hooks.client.mqtt.Client") as mock_mqtt:
        mock_mqtt_instance = MagicMock()
        mock_mqtt.return_value = mock_mqtt_instance
        
        with TelemetryClient() as client:
            assert client.is_connected
            mock_mqtt_instance.connect.assert_called_once()
            mock_mqtt_instance.loop_start.assert_called_once()
            
            client.send("Agent", "/path", "Acting")
            
            # publish should be called, but not a new connect/disconnect
            mock_mqtt_instance.publish.assert_called_once()
            assert mock_mqtt_instance.connect.call_count == 1
            mock_mqtt_instance.disconnect.assert_not_called()
            
        # After context, it should disconnect
        assert not client.is_connected
        mock_mqtt_instance.loop_stop.assert_called_once()
        mock_mqtt_instance.disconnect.assert_called_once()
