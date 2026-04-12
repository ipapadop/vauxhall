"""MQTT subscriber tests for the Vauxhall Dashboard."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from vauxhall.dashboard.mqtt_client import DashboardSubscriber


def test_dashboard_subscriber_on_message() -> None:
    """Test that valid JSON messages trigger the callback."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback)

    msg: Any = MagicMock()
    msg.payload = json.dumps({"agent": "test", "activity": "working"}).encode()
    msg.topic = "vauxhall/agents/test/activity"

    subscriber._on_message(None, None, msg)

    callback.assert_called_once_with({"agent": "test", "activity": "working"})


def test_dashboard_subscriber_on_message_invalid_json() -> None:
    """Test that invalid JSON messages are handled silently."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback)

    msg: Any = MagicMock()
    msg.payload = b"invalid json"
    msg.topic = "vauxhall/agents/test/activity"

    # Should not raise exception and callback should not be called
    subscriber._on_message(None, None, msg)

    callback.assert_not_called()


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_dashboard_subscriber_start_stop(mock_client_class: MagicMock) -> None:
    """Test the subscriber lifecycle (start and stop)."""
    mock_client = mock_client_class.return_value
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, host="test_host", port=1234)

    subscriber.start()

    mock_client.connect.assert_called_once_with("test_host", 1234, keepalive=60)
    mock_client.loop_start.assert_called_once()

    # Manually trigger on_connect to verify subscriptions
    from unittest.mock import call

    subscriber._on_connect(mock_client, None, {}, 0, None)

    mock_client.subscribe.assert_has_calls(
        [call("vauxhall/agents/+/activity"), call("vauxhall/agents/+/status")],
        any_order=True,
    )

    subscriber.stop()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()
