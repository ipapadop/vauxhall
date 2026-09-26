# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for sending prompts from the dashboard and receiving acknowledgments."""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace

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


@dataclass
class FakeMqtt:
    """Records what the subscriber asks its MQTT client to do."""

    connected: bool = True
    result_code: int = mqtt_client.mqtt.MQTT_ERR_SUCCESS
    published: list[tuple[str, str, dict[str, object]]] = field(default_factory=list)
    subscriptions: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def is_connected(self) -> bool:
        """Report the connection state.

        Returns:
            Whether the fake is connected.
        """
        return self.connected

    def publish(self, topic: str, payload: str, **options: object) -> SimpleNamespace:
        """Record a publication.

        Args:
            topic: The topic.
            payload: The payload.
            **options: The QoS and retain flag.

        Returns:
            A result carrying the configured return code.
        """
        self.published.append((topic, payload, options))
        return SimpleNamespace(rc=self.result_code)

    def subscribe(self, topic: str, **options: object) -> None:
        """Record a subscription.

        Args:
            topic: The topic filter.
            **options: The QoS.
        """
        self.subscriptions.append((topic, options))


@dataclass
class Received:
    """Everything the subscriber handed to its callbacks."""

    telemetry: list[dict[str, object]] = field(default_factory=list)
    acks: list[dict[str, str]] = field(default_factory=list)


def make_subscriber(
    *, with_ack_callback: bool = True
) -> tuple[DashboardSubscriber, Received, FakeMqtt]:
    """Create a subscriber with a fake MQTT client and recording callbacks.

    Args:
        with_ack_callback: Whether to register an acknowledgment callback.

    Returns:
        The subscriber, what its callbacks receive, and its fake client.
    """
    received = Received()
    subscriber = DashboardSubscriber(
        received.telemetry.append,
        lambda _: None,
        ack_callback=received.acks.append if with_ack_callback else None,
    )
    fake = FakeMqtt()
    subscriber.client = fake  # type: ignore[assignment]
    return subscriber, received, fake


def message(topic: str, payload: bytes) -> SimpleNamespace:
    """Build the parts of an MQTT message the subscriber reads.

    Args:
        topic: The topic.
        payload: The payload.

    Returns:
        The message.
    """
    return SimpleNamespace(topic=topic, payload=payload)


def ack_message(payload: bytes) -> SimpleNamespace:
    """Build an acknowledgment message for one session.

    Args:
        payload: The message payload.

    Returns:
        The message.
    """
    return message(session_topic("codex", "native:1", "ack"), payload)


def test_send_prompt_publishes_at_qos_one_without_retain() -> None:
    """A prompt goes to the session's topic, never retained."""
    subscriber, _, fake = make_subscriber()

    message_id = subscriber.send_prompt("Codex", "native:1", "run the tests")

    ((topic, payload, options),) = fake.published
    assert topic == session_topic("codex", "native:1", PROMPT_KIND)
    assert options == {"qos": 1, "retain": False}
    assert parse_prompt(payload.encode()) == (message_id, "run the tests")


def test_send_prompt_rejects_unsafe_text_without_publishing() -> None:
    """Text that could break out of a terminal paste never reaches the broker."""
    subscriber, _, fake = make_subscriber()

    with pytest.raises(ValueError, match="control"):
        subscriber.send_prompt("codex", "s", "\x1b[201~")

    assert fake.published == []


def test_send_prompt_requires_a_broker_connection() -> None:
    """A prompt is not queued for later while the broker is unreachable."""
    subscriber, _, fake = make_subscriber()
    fake.connected = False

    with pytest.raises(ConnectionError, match="Not connected"):
        subscriber.send_prompt("codex", "s", "hello")

    assert fake.published == []


def test_send_prompt_reports_a_publish_error() -> None:
    """A refused publication is an error rather than a silent success."""
    subscriber, _, fake = make_subscriber()
    fake.result_code = 4

    with pytest.raises(ConnectionError, match="did not accept"):
        subscriber.send_prompt("codex", "s", "hello")


def test_subscriber_subscribes_to_acknowledgments() -> None:
    """Connecting subscribes to every session's acknowledgment topic."""
    subscriber, _, fake = make_subscriber()

    subscriber._on_connect(fake, None, None, 0, None)  # type: ignore[arg-type]

    assert (ACK_TOPIC_FILTER, {"qos": 1}) in fake.subscriptions


def test_subscriber_forwards_valid_acknowledgments() -> None:
    """A relay's acknowledgment reaches the ack callback, not the telemetry one."""
    subscriber, received, _ = make_subscriber()

    subscriber._on_message(
        None,
        None,
        ack_message(format_ack("id-1", "delivered").encode()),  # type: ignore[arg-type]
    )

    assert received.acks == [{"id": "id-1", "status": "delivered"}]
    assert received.telemetry == []


def test_subscriber_drops_invalid_acknowledgments() -> None:
    """A malformed acknowledgment is dropped, never treated as telemetry."""
    subscriber, received, _ = make_subscriber()

    subscriber._on_message(None, None, ack_message(b"not json"))  # type: ignore[arg-type]

    assert received.acks == []
    assert received.telemetry == []


def test_subscriber_ignores_prompts_on_the_shared_broker() -> None:
    """The dashboard never acts on prompt topics, including its own."""
    subscriber, received, _ = make_subscriber()

    subscriber._on_message(
        None,
        None,
        message(session_topic("codex", "s", PROMPT_KIND), b"{}"),  # type: ignore[arg-type]
    )

    assert received.acks == []
    assert received.telemetry == []


def test_subscriber_without_ack_callback_drops_acknowledgments() -> None:
    """A subscriber built without a callback tolerates acknowledgments."""
    subscriber, received, _ = make_subscriber(with_ack_callback=False)

    subscriber._on_message(
        None,
        None,
        ack_message(format_ack("id-1", "delivered").encode()),  # type: ignore[arg-type]
    )

    assert received.acks == []


@dataclass
class FakeWindow:
    """Records the events sent to the frontend."""

    fail: bool = False
    events: list[tuple[str, object]] = field(default_factory=list)

    def invoke(self, name: str, data: object) -> None:
        """Record an event, or fail like a destroyed window.

        Args:
            name: The event name.
            data: The event payload.

        Raises:
            RuntimeError: When configured to fail.
        """
        if self.fail:
            message = "window gone"
            raise RuntimeError(message)
        self.events.append((name, data))


@dataclass
class FakeSubscriber:
    """Stands in for the subscriber a dashboard publishes prompts through."""

    error: Exception | None = None
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def send_prompt(self, agent: str, session_id: str, text: str) -> str:
        """Record a prompt, or fail with the configured error.

        Args:
            agent: The agent name.
            session_id: The session identity.
            text: The prompt.

        Returns:
            A message identifier.

        Raises:
            Exception: The configured error, when there is one.
        """
        if self.error is not None:
            raise self.error
        self.sent.append((agent, session_id, text))
        return "id-1"


def make_dashboard(
    subscriber: FakeSubscriber | None = None, window: FakeWindow | None = None
) -> DashboardApp:
    """Create a dashboard with a fake window and subscriber.

    Args:
        subscriber: The subscriber, or ``None`` for a dashboard without one.
        window: The window, defaulting to one that records events.

    Returns:
        The dashboard.
    """
    dashboard = DashboardApp(SimpleNamespace())  # type: ignore[arg-type]
    dashboard.window = window or FakeWindow()
    dashboard.mqtt = subscriber  # type: ignore[assignment]
    return dashboard


def test_dashboard_send_prompt_returns_the_message_id() -> None:
    """A published prompt returns the identifier its acknowledgment carries."""
    subscriber = FakeSubscriber()
    dashboard = make_dashboard(subscriber)

    assert dashboard.send_prompt("codex", "s", "hi") == {"ok": True, "id": "id-1"}
    assert subscriber.sent == [("codex", "s", "hi")]


def test_dashboard_send_prompt_reports_errors() -> None:
    """An error the user can act on is returned rather than raised."""
    dashboard = make_dashboard(FakeSubscriber(error=ValueError("Prompt is empty")))

    assert dashboard.send_prompt("codex", "s", "hi") == {
        "ok": False,
        "error": "Prompt is empty",
    }


def test_dashboard_send_prompt_without_a_subscriber() -> None:
    """Before the subscriber exists there is nothing to publish through."""
    assert make_dashboard().send_prompt("codex", "s", "hi")["ok"] is False


def test_dashboard_forwards_acknowledgments_when_ready() -> None:
    """The frontend is told how a prompt fared."""
    dashboard = make_dashboard()
    dashboard.ipc.is_ready = True

    dashboard.on_ack({"id": "id-1", "status": "delivered"})

    assert dashboard.window.events == [
        ("prompt-ack", {"id": "id-1", "status": "delivered"})
    ]


def test_dashboard_drops_acknowledgments_before_ready() -> None:
    """No card can be waiting for an acknowledgment before the frontend is ready."""
    dashboard = make_dashboard()

    dashboard.on_ack({"id": "id-1", "status": "delivered"})

    assert dashboard.window.events == []


def test_dashboard_survives_a_window_error_on_acknowledgment() -> None:
    """A failing window never escapes into the MQTT thread."""
    dashboard = make_dashboard(window=FakeWindow(fail=True))
    dashboard.ipc.is_ready = True

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
    calls: list[tuple[str, str, str]] = []

    def send(agent: str, session_id: str, text: str) -> dict[str, object]:
        """Record a prompt.

        Args:
            agent: The agent name.
            session_id: The session identity.
            text: The prompt.

        Returns:
            A successful result.
        """
        calls.append((agent, session_id, text))
        return {"ok": True, "id": "id-1"}

    result = json.loads(DashboardIPC(on_send_prompt=send).send_prompt(prompt_request()))

    assert result == {"ok": True, "id": "id-1"}
    assert calls == [("Codex", "native:1", "hello")]


@pytest.mark.parametrize("payload", ["not json", prompt_request(agent="")])
def test_ipc_send_prompt_rejects_invalid_requests(payload: str) -> None:
    """A request that isn't an object with an agent, session, and text is refused.

    Args:
        payload: An invalid request.
    """
    calls: list[str] = []

    def send(*arguments: str) -> dict[str, object]:
        """Record a prompt that should never be sent.

        Args:
            *arguments: The agent, session identity, and prompt.

        Returns:
            A successful result.
        """
        calls.append(arguments[2])
        return {"ok": True}

    assert (
        json.loads(DashboardIPC(on_send_prompt=send).send_prompt(payload))["ok"]
        is False
    )
    assert calls == []


def test_ipc_send_prompt_hides_unexpected_errors() -> None:
    """An unexpected failure is reported without its details."""

    def send(*_: str) -> dict[str, object]:
        """Fail like an unexpected bug.

        Raises:
            RuntimeError: Always.
        """
        message = "secret"
        raise RuntimeError(message)

    result = json.loads(DashboardIPC(on_send_prompt=send).send_prompt(prompt_request()))

    assert result == {"ok": False, "error": "The prompt could not be sent"}
