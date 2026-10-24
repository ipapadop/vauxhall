# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry hook client."""

import json
import logging
import socket
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import MQTTConfig
from vauxhall.hooks.client import format_message, publish
from vauxhall.hooks.config import HookConfig

EVENT = {
    "agent": "Gemini",
    "workspace": "/home/user/project",
    "session_id": "native:test-session",
    "state": "Acting",
    "details": {"tool": "grep"},
}


class FakeClock:
    """Monotonic clock that only the fake publication results advance."""

    def __init__(self) -> None:
        """Start the clock at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current time.

        Returns:
            The current time in seconds.
        """
        return self.now


class FakePublishResult:
    """Controllable MQTT publication result."""

    def __init__(
        self,
        *,
        published: bool = True,
        clock: FakeClock | None = None,
        wait_seconds: float = 0.0,
    ) -> None:
        """Initialize the result with its final publication state.

        Args:
            published: Whether the message is reported as delivered.
            clock: Clock that a wait advances, if any.
            wait_seconds: How far a wait advances the clock.
        """
        self.published = published
        self.clock = clock
        self.wait_seconds = wait_seconds
        self.wait_timeout: float | None = None

    def wait_for_publish(self, timeout: float) -> None:
        """Record the bounded delivery wait and let time pass.

        Args:
            timeout: The bounded delivery wait, recorded.
        """
        self.wait_timeout = timeout
        if self.clock is not None:
            self.clock.now += self.wait_seconds

    def is_published(self) -> bool:
        """Report whether the message was delivered.

        Returns:
            Whether the message was delivered.
        """
        return self.published


class FakeMQTTClient:
    """Small deterministic substitute for the external MQTT client."""

    def __init__(
        self,
        *publish_results: FakePublishResult,
        fail_connect: bool = False,
        fail_loop_start: bool = False,
    ) -> None:
        """Initialize the client with controllable publish and connect results.

        Args:
            *publish_results: Results returned by successive ``publish`` calls;
                delivered results when exhausted.
            fail_connect: Whether ``connect`` raises ``OSError``.
            fail_loop_start: Whether ``loop_start`` raises ``RuntimeError``.
        """
        self.events: list[str] = []
        self.publish_results = list(publish_results)
        self.fail_connect = fail_connect
        self.fail_loop_start = fail_loop_start
        self.connect_timeout = 5.0
        self.connected_to: tuple[str, int, int] | None = None
        self.published: list[tuple[str, dict, int]] = []
        self.results: list[FakePublishResult] = []

    def connect(self, host: str, port: int, *, keepalive: int) -> None:
        """Record a connection attempt and optionally fail it.

        Args:
            host: Broker hostname.
            port: Broker port.
            keepalive: Keepalive interval.

        Raises:
            OSError: If the client was built to fail connecting.
        """
        self.events.append("connect")
        self.connected_to = (host, port, keepalive)
        if self.fail_connect:
            raise OSError

    def loop_start(self) -> None:
        """Record network-loop startup and optionally fail it.

        Raises:
            RuntimeError: If the client was built to fail starting its loop.
        """
        self.events.append("loop_start")
        if self.fail_loop_start:
            raise RuntimeError

    def publish(self, topic: str, payload: str, *, qos: int = 0) -> FakePublishResult:
        """Record publication and return its delivery result.

        Args:
            topic: Topic the message is published to.
            payload: The message payload.
            qos: Requested quality of service.

        Returns:
            The delivery result.
        """
        self.events.append("publish")
        self.published.append((topic, json.loads(payload), qos))
        result = (
            self.publish_results.pop(0) if self.publish_results else FakePublishResult()
        )
        self.results.append(result)
        return result

    def disconnect(self) -> None:
        """Record disconnect."""
        self.events.append("disconnect")

    def loop_stop(self) -> None:
        """Record network-loop shutdown."""
        self.events.append("loop_stop")


def _publish(mqtt_client: FakeMQTTClient, *events: dict) -> bool:
    """Publish events through a fake MQTT client to a fixed broker.

    Args:
        mqtt_client: The fake MQTT client.
        *events: The telemetry events.

    Returns:
        What ``publish`` returned.
    """
    with patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client):
        return publish(events, MQTTConfig(host="test_host", port=1234, keepalive=30))


def test_format_message_adds_the_schema_version() -> None:
    """A formatted event is the documented wire payload."""
    assert json.loads(format_message({**EVENT, "env": "remote"})) == {
        "schema_version": 1,
        **EVENT,
        "env": "remote",
    }


def test_format_message_keeps_its_schema_version() -> None:
    """An event can't replace the schema version the client publishes."""
    payload = json.loads(format_message({**EVENT, "schema_version": 2}))

    assert payload["schema_version"] == 1


def test_format_message_rejects_empty_session_id() -> None:
    """A producer cannot emit telemetry without stable session identity."""
    with pytest.raises(ValueError, match="session_id must be a non-empty string"):
        format_message({**EVENT, "session_id": ""})


def test_publish_sends_every_event_over_one_connection() -> None:
    """A batch connects once, publishes each event at QoS 1, then closes."""
    mqtt_client = FakeMQTTClient()
    second = {**EVENT, "state": "Idle", "details": {}}

    assert _publish(mqtt_client, EVENT, second)

    # A hook's connection lasts about a second, and paho times the TLS
    # handshake with the keepalive, so hooks ignore the configured one.
    assert mqtt_client.connected_to == ("test_host", 1234, 1)
    assert mqtt_client.connect_timeout == 1.0
    assert mqtt_client.published == [
        ("vauxhall/agents/gemini/activity", {"schema_version": 1, **EVENT}, 1),
        ("vauxhall/agents/gemini/activity", {"schema_version": 1, **second}, 1),
    ]
    assert mqtt_client.events == [
        "connect",
        "loop_start",
        "publish",
        "publish",
        "disconnect",
        "loop_stop",
    ]


def test_publish_shares_one_deadline_across_acknowledgments() -> None:
    """Waiting for several acknowledgments takes one second in total."""
    clock = FakeClock()
    mqtt_client = FakeMQTTClient(
        FakePublishResult(clock=clock, wait_seconds=0.75),
        FakePublishResult(clock=clock, wait_seconds=0.75),
        FakePublishResult(clock=clock),
    )

    with patch("vauxhall.hooks.client.time.monotonic", clock):
        assert _publish(mqtt_client, EVENT, EVENT, EVENT)

    waits = [result.wait_timeout for result in mqtt_client.results]
    assert waits == [1.0, 0.25, 0.0]


def test_publish_returns_false_when_an_acknowledgment_times_out() -> None:
    """One unacknowledged event fails the batch, which still closes cleanly."""
    mqtt_client = FakeMQTTClient(
        FakePublishResult(), FakePublishResult(published=False)
    )

    assert not _publish(mqtt_client, EVENT, EVENT)
    assert mqtt_client.events[-2:] == ["disconnect", "loop_stop"]


class FailingPublishResult(FakePublishResult):
    """A publication that paho reports as failed."""

    def wait_for_publish(self, timeout: float) -> None:
        """Fail the way paho does for a message it could not send.

        Args:
            timeout: The bounded delivery wait.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError(timeout)


def test_publish_closes_the_connection_when_publishing_fails() -> None:
    """A failed publication fails the batch, which still closes cleanly."""
    mqtt_client = FakeMQTTClient(FailingPublishResult())

    assert not _publish(mqtt_client, EVENT)
    assert mqtt_client.events[-2:] == ["disconnect", "loop_stop"]


def test_publish_skips_invalid_events_and_sends_the_rest() -> None:
    """An invalid event is dropped without losing the valid ones."""
    mqtt_client = FakeMQTTClient()
    invalid = {**EVENT, "details": {"path": Path()}}

    assert not _publish(mqtt_client, invalid, EVENT)
    assert [payload for _, payload, _ in mqtt_client.published] == [
        {"schema_version": 1, **EVENT}
    ]


@pytest.mark.parametrize(
    "event",
    [{**EVENT, "details": {"path": Path()}}, {"state": "Acting"}],
    ids=["unserializable", "missing-agent"],
)
def test_publish_without_a_valid_event_never_connects(event: dict) -> None:
    """A batch with nothing valid to send doesn't touch the broker.

    Args:
        event: The case's invalid event.
    """
    mqtt_client = FakeMQTTClient()

    assert not _publish(mqtt_client, event)
    assert mqtt_client.events == []


def test_publish_closes_the_connection_when_the_network_loop_fails() -> None:
    """A network loop that can't start fails the batch without raising."""
    mqtt_client = FakeMQTTClient(fail_loop_start=True)

    assert not _publish(mqtt_client, EVENT)
    assert mqtt_client.events == ["connect", "loop_start", "disconnect", "loop_stop"]


def test_publish_without_events_succeeds_without_connecting() -> None:
    """An empty batch has nothing to deliver, so nothing fails."""
    mqtt_client = FakeMQTTClient()

    assert _publish(mqtt_client)
    assert mqtt_client.events == []


def test_publish_logs_how_many_events_were_delivered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The success log covers the whole batch, not only its first topic.

    Args:
        caplog: Pytest log capture fixture.
    """
    with caplog.at_level(logging.DEBUG, logger="vauxhall.hooks.client"):
        assert _publish(FakeMQTTClient(), EVENT, {**EVENT, "agent": "Codex"})

    assert "Successfully sent telemetry (2 events)" in caplog.text


def test_publish_returns_false_when_connecting_fails() -> None:
    """A broker that refuses the connection fails the batch without raising."""
    mqtt_client = FakeMQTTClient(fail_connect=True)

    assert not _publish(mqtt_client, EVENT)
    assert mqtt_client.events == ["connect"]


def test_publish_uses_hook_settings_by_default(tmp_path: Path) -> None:
    """Without explicit settings, the batch goes to the hooks file's broker.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_file = tmp_path / "vauxhall_hooks.json"
    data = {"mqtt": {"host": "hook_host", "port": 9999, "keepalive": 120}}
    config_file.write_text(json.dumps(data), encoding="utf-8")
    mqtt_client = FakeMQTTClient()

    with (
        patch("vauxhall.hooks.client.settings", HookConfig.load(config_file)),
        patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client),
    ):
        assert publish([EVENT])

    assert mqtt_client.connected_to == ("hook_host", 9999, 1)


def test_publish_gives_up_on_a_stalled_tls_handshake() -> None:
    """A broker that accepts the connection but never answers can't hold a hook.

    paho times the TLS handshake with the keepalive, not ``connect_timeout``.
    """
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        config = MQTTConfig(
            host="127.0.0.1", port=silent.getsockname()[1], keepalive=10, tls=True
        )
        start = time.monotonic()

        assert not publish([EVENT], config)

    assert time.monotonic() - start < 5
