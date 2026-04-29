# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for config injection in MQTT components."""

from unittest.mock import MagicMock

from vauxhall.dashboard.config import dashboard_settings
from vauxhall.hooks.config import hook_settings
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.hooks.client import TelemetryClient


def test_dashboard_subscriber_uses_settings_by_default() -> None:
    """Verify that DashboardSubscriber uses dashboard_settings.mqtt for default host and port."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(callback, MagicMock())

    assert subscriber.host == dashboard_settings.mqtt.host
    assert subscriber.port == dashboard_settings.mqtt.port


def test_telemetry_client_uses_settings_by_default() -> None:
    """Verify that TelemetryClient uses hook_settings.mqtt for default host and port."""
    client = TelemetryClient()

    assert client.host == hook_settings.mqtt.host
    assert client.port == hook_settings.mqtt.port


def test_dashboard_subscriber_overrides_settings() -> None:
    """Verify that DashboardSubscriber can still override settings."""
    callback = MagicMock()
    subscriber = DashboardSubscriber(
        callback, MagicMock(), host="override_host", port=9999
    )

    assert subscriber.host == "override_host"
    assert subscriber.port == 9999


def test_telemetry_client_overrides_settings() -> None:
    """Verify that TelemetryClient can still override settings."""
    client = TelemetryClient(host="override_host", port=9999)

    assert client.host == "override_host"
    assert client.port == 9999
