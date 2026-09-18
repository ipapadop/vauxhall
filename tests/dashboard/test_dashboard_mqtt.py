# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""MQTT subscriber tests for the Vauxhall Dashboard."""

import json
from threading import Event, Thread
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.mqtt_client import DashboardSubscriber


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
def test_stop_reports_disconnected_once(mock_client_class: MagicMock) -> None:
    """Stopping an active subscriber is idempotent and reports once.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    subscriber._loop_started = True

    subscriber.stop()
    subscriber.stop()

    status_callback.assert_called_once_with("Disconnected")
    mock_client_class.return_value.disconnect.assert_called_once_with()
    mock_client_class.return_value.loop_stop.assert_called_once_with()


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_stop_cleans_up_loop_when_disconnect_raises(
    mock_client_class: MagicMock,
) -> None:
    """A disconnect failure cannot leave the MQTT network loop running.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    subscriber._loop_started = True
    mock_client = mock_client_class.return_value
    mock_client.disconnect.side_effect = RuntimeError("disconnect failed")

    with pytest.raises(RuntimeError, match="disconnect failed"):
        subscriber.stop()

    mock_client.loop_stop.assert_called_once_with()
    assert subscriber._loop_started is False
    status_callback.assert_called_once_with("Disconnected")


@patch("vauxhall.dashboard.mqtt_client.mqtt.Client")
def test_stop_publishes_terminal_status_after_in_progress_connect_callback(
    mock_client_class: MagicMock,
) -> None:
    """A callback that began before stopping cannot overwrite Disconnected.

    Args:
        mock_client_class: Mock replacing
            ``vauxhall.dashboard.mqtt_client.mqtt.Client``.
    """
    callback_entered = Event()
    release_callback = Event()
    statuses: list[str] = []

    class BlockingSuccessCode:
        """Success reason code that holds the connect callback open while compared."""

        __hash__ = object.__hash__

        def __eq__(self, value: object) -> bool:
            """Hold the connect callback open, then compare as success.

            Args:
                value: The reason code being compared against.

            Returns:
                Whether the value is the success code zero.
            """
            callback_entered.set()
            assert release_callback.wait(timeout=1)
            return value == 0

    client = mock_client_class.return_value
    subscriber = DashboardSubscriber(MagicMock(), statuses.append)
    subscriber._loop_started = True
    callback = Thread(
        target=subscriber._on_connect,
        args=(client, None, {}, BlockingSuccessCode(), None),
    )
    callback.start()
    assert callback_entered.wait(timeout=1)

    def join_paho_loop() -> None:
        """Release the in-flight callback and wait for it, as loop_stop() does."""
        release_callback.set()
        callback.join(timeout=1)
        assert not callback.is_alive()

    client.loop_stop.side_effect = join_paho_loop
    subscriber.stop()

    assert statuses == ["Connected to Agent Fleet", "Disconnected"]


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
    subscriber.stop()
    mock_client.loop_start.assert_not_called()
    mock_client.loop_stop.assert_not_called()
    mock_client.disconnect.assert_not_called()
