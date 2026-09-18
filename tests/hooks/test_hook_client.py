# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry hook client."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.hooks.client import TelemetryClient, format_message


class FakePublishResult:
    """Controllable MQTT publication result."""

    def __init__(self, *, published: bool = True) -> None:
        """Initialize the result with its final publication state.

        Args:
            published: Whether the message is reported as delivered.
        """
        self.published = published
        self.wait_timeout: float | None = None

    def wait_for_publish(self, timeout: float) -> None:
        """Record the bounded delivery wait.

        Args:
            timeout: The bounded delivery wait, recorded.
        """
        self.wait_timeout = timeout

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
        publish_result: FakePublishResult | None = None,
        *,
        fail_connect: bool = False,
    ) -> None:
        """Initialize the client with controllable publish and connect results.

        Args:
            publish_result: Result returned by ``publish``.
            fail_connect: Whether ``connect`` raises ``OSError``.
        """
        self.events: list[str] = []
        self.publish_result = publish_result or FakePublishResult()
        self.fail_connect = fail_connect
        self.publish_qos: int | None = None

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
        if self.fail_connect:
            raise OSError

    def loop_start(self) -> None:
        """Record network-loop startup."""
        self.events.append("loop_start")

    def publish(self, topic: str, payload: str, *, qos: int = 0) -> FakePublishResult:
        """Record publication and return its delivery result.

        Args:
            topic: Topic the message is published to.
            payload: The message payload.
            qos: Requested quality of service, recorded.

        Returns:
            The delivery result.
        """
        self.events.append("publish")
        self.publish_qos = qos
        return self.publish_result

    def disconnect(self) -> None:
        """Record disconnect."""
        self.events.append("disconnect")

    def loop_stop(self) -> None:
        """Record network-loop shutdown."""
        self.events.append("loop_stop")


def test_format_message() -> None:
    """Formatted telemetry must include schema and session identity."""
    message = format_message(
        "Gemini",
        "/home/user/project",
        "Acting",
        "native:session-1",
        tool="grep",
    )

    assert json.loads(message) == {
        "schema_version": 1,
        "agent": "Gemini",
        "workspace": "/home/user/project",
        "session_id": "native:session-1",
        "state": "Acting",
        "details": {"tool": "grep"},
    }


def test_format_message_rejects_empty_session_id() -> None:
    """A producer cannot emit telemetry without stable session identity."""
    with pytest.raises(ValueError, match="session_id must be a non-empty string"):
        format_message("Gemini", "/workspace", "Acting", "")


def test_one_shot_send_waits_for_delivery_and_cleans_up() -> None:
    """An ad-hoc send confirms delivery and closes MQTT in protocol order."""
    mqtt_client = FakeMQTTClient()
    with patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client):
        client = TelemetryClient(host="test_host", port=1234)

    assert client.send(
        "Gemini",
        "/home/user/project",
        "Acting",
        "native:test-session",
        tool="grep",
    )
    assert mqtt_client.publish_qos == 1
    assert mqtt_client.publish_result.wait_timeout == 1.0
    assert mqtt_client.events == [
        "connect",
        "loop_start",
        "publish",
        "disconnect",
        "loop_stop",
    ]


def test_send_returns_false_when_publish_times_out() -> None:
    """A publication not acknowledged within the deadline is unsuccessful."""
    mqtt_client = FakeMQTTClient(FakePublishResult(published=False))
    with patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client):
        client = TelemetryClient()

    assert not client.send(
        "Gemini", "/home/user/project", "Acting", "native:test-session"
    )
    assert mqtt_client.events[-2:] == ["disconnect", "loop_stop"]


def test_send_handles_serialization_failure() -> None:
    """Invalid detail values fail silently without touching the broker."""
    mqtt_client = FakeMQTTClient()
    with patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client):
        client = TelemetryClient()

    assert not client.send(
        "Gemini",
        "/home/user/project",
        "Acting",
        "native:test-session",
        path=Path(),
    )
    assert mqtt_client.events == []


def test_context_manager_waits_for_delivery_and_cleans_up() -> None:
    """Persistent sends confirm delivery and defer cleanup until context exit."""
    mqtt_client = FakeMQTTClient()
    with (
        patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client),
        TelemetryClient() as client,
    ):
        assert client.is_connected
        assert client.send("Agent", "/path", "Acting", "native:test-session")
        assert mqtt_client.publish_result.wait_timeout == 1.0
        assert mqtt_client.events == ["connect", "loop_start", "publish"]

    assert not client.is_connected
    assert mqtt_client.events[-2:] == ["disconnect", "loop_stop"]


def test_failed_context_connection_is_not_retried_by_send() -> None:
    """A failed managed connection remains failed for that context."""
    mqtt_client = FakeMQTTClient(fail_connect=True)
    with (
        patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client),
        TelemetryClient() as client,
    ):
        assert not client.is_connected
        assert not client.send("Agent", "/path", "Acting", "native:test-session")

    assert mqtt_client.events == ["connect"]
