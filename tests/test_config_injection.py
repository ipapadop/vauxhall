# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for config injection in MQTT components."""

from unittest.mock import MagicMock

from vauxhall.config import settings
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.hooks.client import TelemetryClient


def test_dashboard_subscriber_uses_settings_by_default() -> None:
    """Verify that DashboardSubscriber uses settings.mqtt for default host and port."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock())

    assert subscriber.host == settings.mqtt.host
    assert subscriber.port == settings.mqtt.port


def test_telemetry_client_uses_settings_by_default() -> None:
    """Verify that TelemetryClient uses settings.mqtt for default host and port."""
    client = TelemetryClient()

    assert client.host == settings.mqtt.host
    assert client.port == settings.mqtt.port


def test_dashboard_subscriber_overrides_settings() -> None:
    """Verify that DashboardSubscriber can still override settings."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock(), host="override_host", port=9999)

    assert subscriber.host == "override_host"
    assert subscriber.port == 9999


def test_telemetry_client_overrides_settings() -> None:
    """Verify that TelemetryClient can still override settings."""
    client = TelemetryClient(host="override_host", port=9999)

    assert client.host == "override_host"
    assert client.port == 9999
