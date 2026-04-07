"""Tests for the telemetry hook client."""

import json

from vauxhall.hooks.client import format_message


def test_format_message() -> None:
    """Test that message formatting returns a valid JSON with expected fields."""
    msg = format_message("Gemini", "/tmp/ws", "Acting", tool="grep")
    data = json.loads(msg)
    assert data["agent"] == "Gemini"
    assert data["workspace"] == "/tmp/ws"
    assert data["state"] == "Acting"
    assert data["details"]["tool"] == "grep"


def test_telemetry_client_fail_silently() -> None:
    """Test that TelemetryClient.send fails silently when broker is unreachable."""
    from vauxhall.hooks.client import TelemetryClient

    client = TelemetryClient(host="nonexistent.local", port=1883)
    # This should not raise an exception
    client.send("Gemini", "/tmp/ws", "Acting", tool="grep")
