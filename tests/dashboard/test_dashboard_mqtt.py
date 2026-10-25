# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""MQTT subscriber tests for the Vauxhall Dashboard."""

import json
from threading import Event, current_thread
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from vauxhall.core.prompts import ACK_TOPIC_FILTER
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.mqtt_client import DashboardSubscriber, SubscriberCloser


def valid_event(**overrides: object) -> dict[str, object]:
    """Return a valid version-one dashboard telemetry event.

    Returns:
        The event.
    """
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
    """Drop oversized MQTT bytes without decoding or forwarding telemetry.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        caplog: Pytest log capture fixture.
    """
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
    """Test the subscriber lifecycle (start and stop).

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    mock_client = mock_client_class.return_value
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock(), host="test_host", port=1234)

    subscriber.start()

    mock_client.connect_async.assert_called_once_with("test_host", 1234, keepalive=60)
    mock_client.loop_start.assert_called_once()

    subscriber._on_connect(mock_client, None, {}, 0, None)

    assert mock_client.subscribe.call_args_list == [
        call("vauxhall/agents/+/activity"),
        call(ACK_TOPIC_FILTER, qos=1),
    ]

    closer = SubscriberCloser()
    subscriber.close(closer)
    assert closer.finish(timeout=5)
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


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_subscriber_start_reports_connecting(mock_client_class: MagicMock) -> None:
    """Starting the subscriber reports that an asynchronous connection began.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber.start()

    status_callback.assert_called_once_with("Connecting...")
    mock_client_class.return_value.loop_start.assert_called_once_with()


def test_first_successful_connect_marks_subscriber_connected() -> None:
    """A successful CONNACK records the first completed connection."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber._on_connect(MagicMock(), None, {}, 0, None)

    assert subscriber._ever_connected is True
    status_callback.assert_called_once_with("Connected to Agent Fleet")


def test_refused_connack_reports_safe_retry_status() -> None:
    """A refused connection reports its Paho reason without an exception."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber._on_connect(MagicMock(), None, {}, "Not authorized", None)

    status_callback.assert_called_once_with(
        "Connection failed: Not authorized. Retrying..."
    )


def test_initial_connect_failure_reports_retry() -> None:
    """Paho connection failures report a retry status."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber._on_connect_fail(MagicMock(), None)

    status_callback.assert_called_once_with("Connection failed. Retrying...")


def test_intentional_disconnect_does_not_report_retry() -> None:
    """The disconnect callback is quiet while shutdown is intentional."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    subscriber._stopping = True

    subscriber._on_disconnect(MagicMock(), None, {}, 0, None)

    status_callback.assert_not_called()


def test_successful_connack_while_stopping_is_silent() -> None:
    """A connection callback cannot revive an intentionally stopping subscriber."""
    status_callback = MagicMock()
    client = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    subscriber._stopping = True

    subscriber._on_connect(client, None, {}, 0, None)

    status_callback.assert_not_called()
    client.subscribe.assert_not_called()


def test_refused_connack_while_stopping_is_silent() -> None:
    """A refusal callback cannot replace the intentional terminal status."""
    status_callback = MagicMock()
    client = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    subscriber._stopping = True

    subscriber._on_connect(client, None, {}, "Not authorized", None)

    status_callback.assert_not_called()
    client.subscribe.assert_not_called()


def test_unexpected_disconnect_before_first_connection_reports_retry() -> None:
    """An initial disconnect remains visible to the dashboard."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    subscriber._on_disconnect(MagicMock(), None, {}, 1, None)

    status_callback.assert_called_once_with("Disconnected. Retrying...")


def test_unexpected_disconnect_after_connection_reports_retry() -> None:
    """A lost established connection remains visible to the dashboard."""
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    subscriber._on_connect(MagicMock(), None, {}, 0, None)
    status_callback.reset_mock()

    subscriber._on_disconnect(MagicMock(), None, {}, 1, None)

    status_callback.assert_called_once_with("Disconnected. Retrying...")


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_close_is_idempotent_and_reports_no_status(
    mock_client_class: MagicMock,
) -> None:
    """Closing disconnects at once, leaves the loop to the closer, and is silent.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    client = mock_client_class.return_value
    statuses: list[str] = []
    subscriber = DashboardSubscriber(MagicMock(), statuses.append)
    subscriber.start()
    closer = MagicMock()

    subscriber.close(closer)
    subscriber.close(closer)

    client.disconnect.assert_called_once_with()
    closer.add.assert_called_once_with(subscriber)
    client.loop_stop.assert_not_called()
    assert statuses == ["Connecting..."]


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_close_logs_a_failed_disconnect_and_still_stops_the_loop(
    mock_client_class: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A disconnect failure is logged and cannot leave the network loop running.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
        caplog: Captures the logged errors.
    """
    client = mock_client_class.return_value
    client.disconnect.side_effect = RuntimeError("disconnect failed")
    client.loop_stop.side_effect = RuntimeError("loop_stop failed")
    subscriber = DashboardSubscriber(MagicMock(), MagicMock())
    subscriber.start()
    closer = SubscriberCloser()

    subscriber.close(closer)

    assert closer.finish(timeout=5)
    client.loop_stop.assert_called_once_with()
    assert "Could not disconnect from the MQTT broker" in caplog.text
    assert "Could not stop the MQTT network loop" in caplog.text


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_start_failure_before_loop_ownership_is_cleaned_up(
    mock_client_class: MagicMock,
) -> None:
    """A connection setup failure does not leave a loop to clean up.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    mock_client = mock_client_class.return_value
    mock_client.connect_async.side_effect = RuntimeError("broker unavailable")
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)

    with pytest.raises(RuntimeError, match="broker unavailable"):
        subscriber.start()

    assert subscriber._loop_started is False
    status_callback.assert_has_calls([call("Connecting..."), call("Connection failed")])
    closer = MagicMock()
    subscriber.close(closer)
    closer.add.assert_not_called()
    mock_client.loop_start.assert_not_called()
    mock_client.loop_stop.assert_not_called()
    mock_client.disconnect.assert_not_called()


def test_dashboard_subscriber_uses_settings_by_default() -> None:
    """Without an explicit host and port, the dashboard's MQTT settings apply."""
    subscriber = DashboardSubscriber(MagicMock(), MagicMock())

    assert subscriber.host == settings.mqtt.host
    assert subscriber.port == settings.mqtt.port


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_close_returns_before_the_network_loop_stops(
    mock_client_class: MagicMock,
) -> None:
    """Closing doesn't wait for a network thread stuck in a connect attempt.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    release_loop = Event()

    def stuck_join() -> None:
        """Wait, as loop_stop() does for a thread inside connect()."""
        assert release_loop.wait(timeout=5)

    client = mock_client_class.return_value
    client.loop_stop.side_effect = stuck_join
    subscriber = DashboardSubscriber(MagicMock(), MagicMock())
    subscriber.start()
    closer = SubscriberCloser()

    subscriber.close(closer)

    assert not closer.finish(timeout=0.05)
    release_loop.set()
    assert closer.finish(timeout=5)


def test_closer_stops_loops_one_at_a_time() -> None:
    """A loop stuck in a connect attempt holds back the next, not a new thread."""
    release_first = Event()
    stopped: list[str] = []
    first, second = MagicMock(), MagicMock()
    first.stop_loop.side_effect = lambda: (
        release_first.wait(timeout=5),
        stopped.append("first"),
    )
    second.stop_loop.side_effect = lambda: stopped.append(current_thread().name)
    closer = SubscriberCloser()

    closer.add(first)
    closer.add(second)

    assert not closer.finish(timeout=0.05)
    assert stopped == []
    release_first.set()
    assert closer.finish(timeout=5)
    assert stopped == ["first", "vauxhall-mqtt-closer"]


def test_closer_without_subscribers_finishes_at_once() -> None:
    """A closer that was never given a subscriber has no thread to wait for."""
    assert SubscriberCloser().finish(timeout=0)


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_closed_subscriber_cannot_be_started_again(
    mock_client_class: MagicMock,
) -> None:
    """Close is final, so a restart can't race the closer for the client.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    subscriber = DashboardSubscriber(MagicMock(), MagicMock())
    subscriber.close(MagicMock())

    with pytest.raises(RuntimeError, match="can't be started again"):
        subscriber.start()

    mock_client_class.return_value.connect_async.assert_not_called()


def test_messages_after_close_are_still_forwarded() -> None:
    """Telemetry and acknowledgments a closing client receives still describe agents.

    A prompt's acknowledgment can reach the old client before the new one
    subscribes, and acknowledgments are not replayed.
    """
    callback, ack_callback = MagicMock(), MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock(), ack_callback=ack_callback)
    subscriber.close(MagicMock())

    telemetry = MagicMock(topic="vauxhall/agents/codex/activity")
    telemetry.payload = json.dumps(valid_event()).encode()
    ack = MagicMock(topic="vauxhall/agents/codex/sessions/session-1/ack")
    ack.payload = json.dumps(
        {"schema_version": 1, "id": "a1", "status": "delivered"}
    ).encode()
    subscriber._on_message(subscriber.client, None, telemetry)
    subscriber._on_message(subscriber.client, None, ack)

    callback.assert_called_once_with(valid_event())
    ack_callback.assert_called_once_with({"id": "a1", "status": "delivered"})
