# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry hook client."""

import json

from vauxhall.hooks.client import format_message


def test_format_message() -> None:
    """Test that message formatting returns a valid JSON with expected fields."""
    msg = format_message("Gemini", "/tmp/ws", "Acting", tool="grep")
    data = json.loads(msg)
    assert data["agent"] == "Gemini"
    assert data["workspace"] == "/tmp/ws"
    assert data["state"] == "Acting"
    assert data["details"]["tool"] == "grep"


def test_telemetry_client_fail_silently() -> None:
    """Test that TelemetryClient.send fails silently when broker is unreachable."""
    from vauxhall.hooks.client import TelemetryClient

    client = TelemetryClient(host="nonexistent.local", port=1883)
    # This should not raise an exception
    client.send("Gemini", "/tmp/ws", "Acting", tool="grep")


from unittest.mock import MagicMock, patch  # noqa: E402


@patch("vauxhall.hooks.client.mqtt.Client")
def test_telemetry_client_send_calls(mock_client_class: MagicMock) -> None:
    """Test that TelemetryClient.send calls all expected methods."""
    from vauxhall.hooks.client import TelemetryClient

    mock_client = mock_client_class.return_value
    mock_publish_result = MagicMock()
    mock_client.publish.return_value = mock_publish_result

    client = TelemetryClient(host="test_host", port=1234)
    client.send("Gemini", "/tmp/ws", "Acting", env="local", tool="grep")

    mock_client.connect.assert_called_once_with("test_host", 1234, keepalive=60)
    mock_client.publish.assert_called_once()
    mock_publish_result.wait_for_publish.assert_called_once()
    mock_client.disconnect.assert_called_once()
