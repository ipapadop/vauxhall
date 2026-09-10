# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""MQTT subscriber tests for the Vauxhall Dashboard."""

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.mqtt_client import DashboardSubscriber


def valid_event(**overrides: object) -> dict[str, object]:
    """Return a valid version-one dashboard telemetry event."""
    event: dict[str, object] = {
        "schema_version": 1,
        "agent": "Codex",
        "workspace": "/workspace",
        "session_id": "session-1",
        "state": "Thinking",
        "details": {},
    }
    event.update(overrides)
    return event


def test_dashboard_subscriber_on_message() -> None:
    """Test that valid JSON messages trigger the callback."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock())

    msg: Any = MagicMock()
    event = valid_event()
    msg.payload = json.dumps(event).encode()
    msg.topic = "vauxhall/agents/test/activity"

    subscriber._on_message(None, None, msg)

    callback.assert_called_once_with(event)


def test_dashboard_subscriber_on_message_invalid_json() -> None:
    """Test that invalid JSON messages are handled silently."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock())

    msg: Any = MagicMock()
    msg.payload = b"invalid json"
    msg.topic = "vauxhall/agents/test/activity"

    # Should not raise exception and callback should not be called
    subscriber._on_message(None, None, msg)

    callback.assert_not_called()


def test_dashboard_subscriber_rejects_oversized_payload_before_json_decoding(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Drop oversized MQTT bytes without decoding or forwarding telemetry."""
    monkeypatch.setattr(settings.dashboard, "max_payload_bytes", 4)
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock())
    msg: Any = MagicMock()
    msg.payload = b"12345"
    msg.topic = "vauxhall/agents/test/activity"

    with patch("vauxhall.dashboard.mqtt_client.json.loads") as mock_loads:
        subscriber._on_message(None, None, msg)

    mock_loads.assert_not_called()
    callback.assert_not_called()
    assert "vauxhall/agents/test/activity" in caplog.text
    assert "5" in caplog.text


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_dashboard_subscriber_start_stop(mock_client_class: MagicMock) -> None:
    """Test the subscriber lifecycle (start and stop)."""
    mock_client = mock_client_class.return_value
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock(), host="test_host", port=1234)

    subscriber.start()

    mock_client.connect_async.assert_called_once_with("test_host", 1234, keepalive=60)
    mock_client.loop_start.assert_called_once()

    subscriber._on_connect(mock_client, None, {}, 0, None)

    mock_client.subscribe.assert_has_calls(
        [call("vauxhall/agents/+/activity"), call("vauxhall/agents/+/status")],
        any_order=True,
    )

    subscriber.stop()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()


def test_dashboard_subscriber_on_connect_status() -> None:
    """Test that on_connect triggers the status callback."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber._on_connect(MagicMock(), None, {}, 0, None)
    status_callback.assert_called_with("Connected to Agent Fleet")


def test_dashboard_subscriber_on_disconnect_status() -> None:
    """Test that on_disconnect triggers the status callback."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber._on_disconnect(MagicMock(), None, {}, 1, None)
    status_callback.assert_called_with("Disconnected. Retrying...")
