# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry hook client."""

import json
from pathlib import Path
from unittest.mock import patch

from vauxhall.hooks.client import TelemetryClient, format_message


class FakePublishResult:
    """Controllable MQTT publication result."""

    def __init__(self, *, published: bool = True) -> None:
        """Initialize the result with its final publication state."""
        self.published = published
        self.wait_timeout: float | None = None

    def wait_for_publish(self, timeout: float) -> None:
        """Record the bounded delivery wait."""
        self.wait_timeout = timeout

    def is_published(self) -> bool:
        """Report whether the message was delivered."""
        return self.published


class FakeMQTTClient:
    """Small deterministic substitute for the external MQTT client."""

    def __init__(
        self,
        publish_result: FakePublishResult | None = None,
        *,
        fail_connect: bool = False,
    ) -> None:
        """Initialize the client with controllable publish and connect results."""
        self.events: list[str] = []
        self.publish_result = publish_result or FakePublishResult()
        self.fail_connect = fail_connect

    def connect(self, host: str, port: int, *, keepalive: int) -> None:
        """Record a connection attempt and optionally fail it."""
        self.events.append("connect")
        if self.fail_connect:
            raise OSError

    def loop_start(self) -> None:
        """Record network-loop startup."""
        self.events.append("loop_start")

    def publish(self, topic: str, payload: str) -> FakePublishResult:
        """Record publication and return its delivery result."""
        self.events.append("publish")
        return self.publish_result

    def disconnect(self) -> None:
        """Record disconnect."""
        self.events.append("disconnect")

    def loop_stop(self) -> None:
        """Record network-loop shutdown."""
        self.events.append("loop_stop")


def test_format_message() -> None:
    """Test that message formatting returns a valid JSON with expected fields."""
    msg = format_message("Gemini", "/home/user/project", "Acting", tool="grep")
    data = json.loads(msg)
    assert data["agent"] == "Gemini"
    assert data["workspace"] == "/home/user/project"
    assert data["state"] == "Acting"
    assert data["details"]["tool"] == "grep"


def test_one_shot_send_waits_for_delivery_and_cleans_up() -> None:
    """An ad-hoc send confirms delivery and closes MQTT in protocol order."""
    mqtt_client = FakeMQTTClient()
    with patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client):
        client = TelemetryClient(host="test_host", port=1234)

    assert client.send("Gemini", "/home/user/project", "Acting", tool="grep")
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

    assert not client.send("Gemini", "/home/user/project", "Acting")
    assert mqtt_client.events[-2:] == ["disconnect", "loop_stop"]


def test_send_handles_serialization_failure() -> None:
    """Invalid detail values fail silently without touching the broker."""
    mqtt_client = FakeMQTTClient()
    with patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client):
        client = TelemetryClient()

    assert not client.send("Gemini", "/home/user/project", "Acting", path=Path())
    assert mqtt_client.events == []


def test_context_manager_waits_for_delivery_and_cleans_up() -> None:
    """Persistent sends confirm delivery and defer cleanup until context exit."""
    mqtt_client = FakeMQTTClient()
    with (
        patch("vauxhall.hooks.client.mqtt.Client", return_value=mqtt_client),
        TelemetryClient() as client,
    ):
        assert client.is_connected
        assert client.send("Agent", "/path", "Acting")
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
        assert not client.send("Agent", "/path", "Acting")

    assert mqtt_client.events == ["connect"]
