import json
from unittest.mock import MagicMock, patch

from vauxhall.dashboard.mqtt_client import DashboardSubscriber


def test_dashboard_subscriber_on_message():
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback)

    msg = MagicMock()
    msg.payload = json.dumps({"agent": "test", "activity": "working"}).encode()
    msg.topic = "vauxhall/agents/test/activity"

    subscriber._on_message(None, None, msg)

    callback.assert_called_once_with({"agent": "test", "activity": "working"})


def test_dashboard_subscriber_on_message_invalid_json():
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback)

    msg = MagicMock()
    msg.payload = b"invalid json"
    msg.topic = "vauxhall/agents/test/activity"

    # Should not raise exception and callback should not be called
    subscriber._on_message(None, None, msg)

    callback.assert_not_called()


@patch("paho.mqtt.client.Client")
def test_dashboard_subscriber_start_stop(mock_client_class):
    mock_client = mock_client_class.return_value
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, host="test_host", port=1234)

    subscriber.start()

    mock_client.connect.assert_called_once_with("test_host", 1234)
    mock_client.subscribe.assert_called_once_with("vauxhall/agents/+/activity")
    mock_client.loop_start.assert_called_once()

    subscriber.stop()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()
