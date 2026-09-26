# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for sending prompts from the dashboard and receiving acknowledgments."""

import json
from unittest.mock import MagicMock

import pytest

from vauxhall.core.prompts import (
    ACK_TOPIC_FILTER,
    PROMPT_KIND,
    format_ack,
    parse_prompt,
    session_topic,
)
from vauxhall.dashboard import mqtt_client
from vauxhall.dashboard.app import DashboardApp
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber


@pytest.fixture
def subscriber() -> DashboardSubscriber:
    """Create a subscriber with a connected mock client and mock callbacks.

    Returns:
        The subscriber, with ``ack_callback`` a mock.
    """
    subscriber = DashboardSubscriber(MagicMock(), MagicMock(), ack_callback=MagicMock())
    subscriber.client = MagicMock()
    subscriber.client.is_connected.return_value = True
    subscriber.client.publish.return_value.rc = mqtt_client.mqtt.MQTT_ERR_SUCCESS
    return subscriber


def ack_message(payload: bytes, agent: str = "codex") -> MagicMock:
    """Build an MQTT acknowledgment message.

    Args:
        payload: The message payload.
        agent: The agent in the topic.

    Returns:
        The message.
    """
    message = MagicMock()
    message.topic = session_topic(agent, "native:1", "ack")
    message.payload = payload
    return message


def test_send_prompt_publishes_at_qos_one_without_retain(
    subscriber: DashboardSubscriber,
) -> None:
    """A prompt goes to the session's topic, never retained.

    Args:
        subscriber: The subscriber under test.
    """
    message_id = subscriber.send_prompt("Codex", "native:1", "run the tests")

    ((topic, payload), kwargs) = subscriber.client.publish.call_args
    assert topic == session_topic("codex", "native:1", PROMPT_KIND)
    assert kwargs == {"qos": 1, "retain": False}
    assert parse_prompt(payload.encode()) == (message_id, "run the tests")


def test_send_prompt_uses_a_new_identifier_each_time(
    subscriber: DashboardSubscriber,
) -> None:
    """Acknowledgments can be matched to the prompt they answer.

    Args:
        subscriber: The subscriber under test.
    """
    assert subscriber.send_prompt("codex", "s", "a") != subscriber.send_prompt(
        "codex", "s", "a"
    )


def test_send_prompt_rejects_unsafe_text_without_publishing(
    subscriber: DashboardSubscriber,
) -> None:
    """Text that could break out of a terminal paste never reaches the broker.

    Args:
        subscriber: The subscriber under test.
    """
    with pytest.raises(ValueError, match="control"):
        subscriber.send_prompt("codex", "s", "\x1b[201~")

    subscriber.client.publish.assert_not_called()


def test_send_prompt_requires_a_broker_connection(
    subscriber: DashboardSubscriber,
) -> None:
    """A prompt is not queued for later while the broker is unreachable.

    Args:
        subscriber: The subscriber under test.
    """
    subscriber.client.is_connected.return_value = False

    with pytest.raises(ConnectionError, match="Not connected"):
        subscriber.send_prompt("codex", "s", "hello")

    subscriber.client.publish.assert_not_called()


def test_send_prompt_reports_a_publish_error(subscriber: DashboardSubscriber) -> None:
    """A refused publication is an error rather than a silent success.

    Args:
        subscriber: The subscriber under test.
    """
    subscriber.client.publish.return_value.rc = 4

    with pytest.raises(ConnectionError, match="did not accept"):
        subscriber.send_prompt("codex", "s", "hello")


def test_subscriber_subscribes_to_acknowledgments(
    subscriber: DashboardSubscriber,
) -> None:
    """Connecting subscribes to every session's acknowledgment topic.

    Args:
        subscriber: The subscriber under test.
    """
    client = MagicMock()

    subscriber._on_connect(client, None, MagicMock(), 0, None)

    client.subscribe.assert_any_call(ACK_TOPIC_FILTER, qos=1)


def test_subscriber_forwards_valid_acknowledgments(
    subscriber: DashboardSubscriber,
) -> None:
    """A relay's acknowledgment reaches the callback, not the telemetry one.

    Args:
        subscriber: The subscriber under test.
    """
    subscriber._on_message(
        None, None, ack_message(format_ack("id-1", "delivered").encode())
    )

    subscriber.ack_callback.assert_called_once_with(  # type: ignore[union-attr]
        {"id": "id-1", "status": "delivered"}
    )
    subscriber.callback.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.parametrize("payload", [b"not json", json.dumps({"id": "x"}).encode()])
def test_subscriber_drops_invalid_acknowledgments(
    subscriber: DashboardSubscriber, payload: bytes
) -> None:
    """Malformed acknowledgments are dropped, never treated as telemetry.

    Args:
        subscriber: The subscriber under test.
        payload: An invalid acknowledgment payload.
    """
    subscriber._on_message(None, None, ack_message(payload))

    subscriber.ack_callback.assert_not_called()  # type: ignore[union-attr]
    subscriber.callback.assert_not_called()  # type: ignore[attr-defined]


def test_subscriber_ignores_prompts_on_the_shared_broker(
    subscriber: DashboardSubscriber,
) -> None:
    """The dashboard never acts on prompt topics, including its own.

    Args:
        subscriber: The subscriber under test.
    """
    message = MagicMock()
    message.topic = session_topic("codex", "s", PROMPT_KIND)
    message.payload = b"{}"

    subscriber._on_message(None, None, message)

    subscriber.ack_callback.assert_not_called()  # type: ignore[union-attr]
    subscriber.callback.assert_not_called()  # type: ignore[attr-defined]


def test_subscriber_without_ack_callback_drops_acknowledgments() -> None:
    """A subscriber built without a callback tolerates acknowledgments."""
    subscriber = DashboardSubscriber(MagicMock(), MagicMock())

    subscriber._on_message(
        None, None, ack_message(format_ack("id-1", "delivered").encode())
    )


def make_dashboard() -> DashboardApp:
    """Create a dashboard with a mock window and subscriber.

    Returns:
        The dashboard.
    """
    dashboard = DashboardApp(MagicMock())
    dashboard.window = MagicMock()
    dashboard.mqtt = MagicMock()
    return dashboard


def test_dashboard_send_prompt_returns_the_message_id() -> None:
    """A published prompt returns the identifier its acknowledgment carries."""
    dashboard = make_dashboard()
    dashboard.mqtt.send_prompt.return_value = "id-1"  # type: ignore[union-attr]

    assert dashboard.send_prompt("codex", "s", "hi") == {"ok": True, "id": "id-1"}
    dashboard.mqtt.send_prompt.assert_called_once_with("codex", "s", "hi")  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "error", [ValueError("Prompt must not be empty"), ConnectionError("down")]
)
def test_dashboard_send_prompt_reports_errors(error: Exception) -> None:
    """Errors the user can act on are returned rather than raised.

    Args:
        error: The error the subscriber raises.
    """
    dashboard = make_dashboard()
    dashboard.mqtt.send_prompt.side_effect = error  # type: ignore[union-attr]

    assert dashboard.send_prompt("codex", "s", "hi") == {
        "ok": False,
        "error": str(error),
    }


def test_dashboard_send_prompt_without_a_subscriber() -> None:
    """Before the subscriber exists there is nothing to publish through."""
    dashboard = make_dashboard()
    dashboard.mqtt = None

    assert dashboard.send_prompt("codex", "s", "hi")["ok"] is False


def test_dashboard_forwards_acknowledgments_when_ready() -> None:
    """The frontend is told how a prompt fared."""
    dashboard = make_dashboard()
    dashboard.ipc.is_ready = True

    dashboard.on_ack({"id": "id-1", "status": "delivered"})

    dashboard.window.invoke.assert_called_once_with(
        "prompt-ack", {"id": "id-1", "status": "delivered"}
    )


def test_dashboard_drops_acknowledgments_before_ready() -> None:
    """No card can be waiting for an acknowledgment before the frontend is ready."""
    dashboard = make_dashboard()

    dashboard.on_ack({"id": "id-1", "status": "delivered"})

    dashboard.window.invoke.assert_not_called()


def test_dashboard_survives_a_window_error_on_acknowledgment() -> None:
    """A failing window never escapes into the MQTT thread."""
    dashboard = make_dashboard()
    dashboard.ipc.is_ready = True
    dashboard.window.invoke.side_effect = RuntimeError("window gone")

    dashboard.on_ack({"id": "id-1", "status": "delivered"})


def prompt_request(**overrides: object) -> str:
    """Build a bridge payload for ``send_prompt``.

    Args:
        **overrides: Fields to replace.

    Returns:
        The JSON payload.
    """
    request = {"agent": "Codex", "session_id": "native:1", "text": "hello"}
    request.update(overrides)
    return json.dumps(request)


def test_ipc_send_prompt_calls_the_callback() -> None:
    """The bridge passes a valid request on and returns the result as JSON."""
    callback = MagicMock(return_value={"ok": True, "id": "id-1"})
    ipc = DashboardIPC(on_send_prompt=callback)

    result = json.loads(ipc.send_prompt(prompt_request()))

    assert result == {"ok": True, "id": "id-1"}
    callback.assert_called_once_with("Codex", "native:1", "hello")


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        prompt_request(agent=""),
        prompt_request(session_id=None),
        prompt_request(text=5),
        json.dumps({"agent": "Codex"}),
    ],
)
def test_ipc_send_prompt_rejects_invalid_requests(payload: str) -> None:
    """A request without an agent, session, and text is never acted on.

    Args:
        payload: An invalid request.
    """
    callback = MagicMock()
    ipc = DashboardIPC(on_send_prompt=callback)

    assert json.loads(ipc.send_prompt(payload))["ok"] is False
    callback.assert_not_called()


def test_ipc_send_prompt_without_a_callback() -> None:
    """A bridge without a sender reports an error."""
    assert json.loads(DashboardIPC().send_prompt(prompt_request()))["ok"] is False


def test_ipc_send_prompt_hides_unexpected_errors() -> None:
    """An unexpected failure is reported without its details."""
    ipc = DashboardIPC(on_send_prompt=MagicMock(side_effect=RuntimeError("secret")))

    result = json.loads(ipc.send_prompt(prompt_request()))

    assert result == {"ok": False, "error": "The prompt could not be sent"}
