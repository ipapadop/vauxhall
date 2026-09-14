# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the dashboard settings editor backend."""

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vauxhall.core.config import LoggingConfig, MQTTConfig
from vauxhall.core.config_store import user_config_path
from vauxhall.dashboard.app import DashboardApp
from vauxhall.dashboard.config import UIConfig, dashboard_settings
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.settings_editor import (
    DASHBOARD_FILE,
    HOOKS_FILE,
    describe_settings,
    error_field,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate files, environment, running settings, and the root log level."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(cwd)
    for name in list(os.environ):
        if name.startswith("VAUXHALL_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(dashboard_settings, "mqtt", MQTTConfig())
    monkeypatch.setattr(dashboard_settings, "logging", LoggingConfig())
    monkeypatch.setattr(dashboard_settings, "dashboard", UIConfig())
    root = logging.getLogger()
    level = root.level
    yield
    root.setLevel(level)


@pytest.fixture
def dashboard() -> DashboardApp:
    """Return a dashboard whose frontend is ready and MQTT is not started."""
    app = DashboardApp(MagicMock())
    app.window = MagicMock()
    app.ipc.is_ready = True
    return app


def write_user_file(filename: str, content: str) -> Path:
    """Write raw content to a per-user configuration file."""
    path = user_config_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_describe_settings_lists_every_field() -> None:
    """Every field is described with its constraints, source, and apply mode."""
    described = describe_settings(dashboard_settings)
    fields = {field["key"]: field for field in described["fields"]}

    assert len(fields) == 13
    assert fields["mqtt.port"] == {
        "key": "mqtt.port",
        "section": "mqtt",
        "name": "port",
        "value": 1883,
        "default": 1883,
        "type": "integer",
        "min": 1,
        "max": 65535,
        "choices": None,
        "required": False,
        "source": "default",
        "location": None,
        "editable": True,
        "apply": "reconnect",
    }
    assert fields["mqtt.host"]["required"] is True
    assert fields["logging.level"]["choices"] == [
        "CRITICAL",
        "DEBUG",
        "ERROR",
        "INFO",
        "WARNING",
    ]
    assert fields["logging.level"]["apply"] == "live"
    assert fields["dashboard.debug"]["type"] == "boolean"
    assert fields["dashboard.window_title"]["apply"] == "restart"
    assert described["paths"] == {
        "dashboard": str(user_config_path(DASHBOARD_FILE)),
        "hooks": str(user_config_path(HOOKS_FILE)),
    }
    assert described["hooks_error"] is None


def test_describe_settings_reports_hooks_file_error() -> None:
    """A malformed hooks file disables hook updates without hiding the fields."""
    write_user_file(HOOKS_FILE, "{")

    described = describe_settings(dashboard_settings)

    assert "not valid JSON" in described["hooks_error"]
    assert len(described["fields"]) == 13


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            (
                "Invalid configuration value from /h/vauxhall_dashboard.json:mqtt.port "
                "for mqtt.port: 0; expected an integer in range 1..65535"
            ),
            "mqtt.port",
        ),
        ("mqtt.host cannot be saved to /h/x.json: it is set by X", "mqtt.host"),
        ("Unknown configuration field: mqtt.password", None),
        ("/h/vauxhall_dashboard.json: is not valid JSON", None),
    ],
)
def test_error_field(message: str, expected: str | None) -> None:
    """The field named in an error message is found, ignoring file names."""
    assert error_field(message) == expected


def test_save_applies_live_settings(dashboard: DashboardApp) -> None:
    """Live settings are saved, applied, and sent to the frontend."""
    result = dashboard.save_settings(
        {"dashboard": {"stale_threshold": 300}}, update_hooks=False
    )

    assert result == {
        "ok": True,
        "restart_required": [],
        "reconnecting": False,
        "hooks_updated": False,
        "hooks_error": None,
    }
    assert dashboard_settings.dashboard.stale_threshold == 300
    assert json.loads(user_config_path(DASHBOARD_FILE).read_text()) == {
        "dashboard": {"stale_threshold": 300}
    }
    dashboard.window.invoke.assert_called_once_with(
        "settings-changed", {"stale_threshold": 300, "max_active_agents": 100}
    )


def test_save_applies_logging_level(dashboard: DashboardApp) -> None:
    """A new logging level is applied to the root logger immediately."""
    dashboard.save_settings({"logging": {"level": "DEBUG"}}, update_hooks=False)

    assert logging.getLogger().level == logging.DEBUG


def test_save_reports_restart_required(dashboard: DashboardApp) -> None:
    """Changes that need a restart are reported."""
    result = dashboard.save_settings(
        {"dashboard": {"window_title": "Fleet", "stale_threshold": 60}},
        update_hooks=False,
    )

    assert result["restart_required"] == ["dashboard.window_title"]


def test_frontend_not_notified_before_ready(dashboard: DashboardApp) -> None:
    """Settings changes are not sent to a frontend that is not ready."""
    dashboard.ipc.is_ready = False

    dashboard.save_settings({"dashboard": {"stale_threshold": 60}}, update_hooks=False)

    dashboard.window.invoke.assert_not_called()


def test_invalid_save_changes_nothing(dashboard: DashboardApp) -> None:
    """An invalid value is reported for its field and nothing is saved or applied."""
    result = dashboard.save_settings({"mqtt": {"port": 0}}, update_hooks=False)

    assert result["ok"] is False
    assert result["field"] == "mqtt.port"
    assert result["file"] == "dashboard"
    assert not user_config_path(DASHBOARD_FILE).exists()
    assert dashboard_settings.mqtt.port == 1883
    dashboard.window.invoke.assert_not_called()


def test_environment_field_is_rejected(
    dashboard: DashboardApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A field set by an environment variable is reported as not saved."""
    monkeypatch.setenv("VAUXHALL_MQTT_HOST", "env-broker")

    result = dashboard.save_settings({"mqtt": {"host": "b"}}, update_hooks=False)

    assert result["ok"] is False
    assert result["field"] == "mqtt.host"


def test_mqtt_change_reconnects(dashboard: DashboardApp) -> None:
    """Broker changes stop the subscriber and start one with the new settings."""
    old_subscriber = MagicMock()
    dashboard.mqtt = old_subscriber

    with patch("vauxhall.dashboard.app.DashboardSubscriber") as subscriber_type:
        result = dashboard.save_settings(
            {"mqtt": {"host": "broker", "keepalive": 30}}, update_hooks=False
        )

    assert result["reconnecting"] is True
    assert result["restart_required"] == []
    old_subscriber.stop.assert_called_once_with()
    subscriber_type.assert_called_once_with(
        dashboard.on_telemetry, dashboard.on_status, "broker", 1883
    )
    subscriber_type.return_value.start.assert_called_once_with()
    assert dashboard.mqtt is subscriber_type.return_value
    assert dashboard_settings.mqtt.keepalive == 30


def test_second_mqtt_change_replaces_reconnected_subscriber(
    dashboard: DashboardApp,
) -> None:
    """A later broker change stops the subscriber started by the previous one."""
    dashboard.mqtt = MagicMock()
    first, second = MagicMock(), MagicMock()

    with patch(
        "vauxhall.dashboard.app.DashboardSubscriber", side_effect=[first, second]
    ):
        dashboard.save_settings({"mqtt": {"host": "one"}}, update_hooks=False)
        dashboard.save_settings({"mqtt": {"host": "two"}}, update_hooks=False)

    first.stop.assert_called_once_with()
    second.start.assert_called_once_with()
    assert dashboard.mqtt is second


def test_reconnect_failure_keeps_saved_settings(dashboard: DashboardApp) -> None:
    """A subscriber that fails to start does not undo the saved settings."""
    dashboard.mqtt = MagicMock()

    with patch("vauxhall.dashboard.app.DashboardSubscriber") as subscriber_type:
        subscriber_type.return_value.start.side_effect = OSError("unreachable")
        result = dashboard.save_settings({"mqtt": {"port": 1884}}, update_hooks=False)

    assert result["ok"] is True
    assert dashboard_settings.mqtt.port == 1884


def test_mqtt_change_before_start_does_not_reconnect(dashboard: DashboardApp) -> None:
    """Without a running subscriber, broker changes are only saved."""
    with patch("vauxhall.dashboard.app.DashboardSubscriber") as subscriber_type:
        result = dashboard.save_settings({"mqtt": {"port": 1884}}, update_hooks=False)

    assert result["reconnecting"] is False
    subscriber_type.assert_not_called()


def test_update_hooks_writes_only_mqtt(dashboard: DashboardApp) -> None:
    """Hook updates save only the MQTT changes to the hooks file."""
    result = dashboard.save_settings(
        {"mqtt": {"host": "broker"}, "dashboard": {"stale_threshold": 300}},
        update_hooks=True,
    )

    assert result["hooks_updated"] is True
    assert json.loads(user_config_path(HOOKS_FILE).read_text()) == {
        "mqtt": {"host": "broker"}
    }


def test_invalid_hooks_file_blocks_both_saves(dashboard: DashboardApp) -> None:
    """If the hooks change is invalid, the dashboard file is not written either."""
    write_user_file(HOOKS_FILE, "{")

    result = dashboard.save_settings({"mqtt": {"host": "broker"}}, update_hooks=True)

    assert result["ok"] is False
    assert result["file"] == "hooks"
    assert not user_config_path(DASHBOARD_FILE).exists()
    assert dashboard_settings.mqtt.host == "localhost"


def test_update_hooks_without_mqtt_changes_skips_hooks(
    dashboard: DashboardApp,
) -> None:
    """Hook updates are skipped when no MQTT field changed."""
    write_user_file(HOOKS_FILE, "{")

    result = dashboard.save_settings(
        {"dashboard": {"stale_threshold": 300}}, update_hooks=True
    )

    assert result["ok"] is True
    assert result["hooks_updated"] is False


def test_hooks_write_failure_is_reported(dashboard: DashboardApp) -> None:
    """A hooks file that cannot be written is reported after the dashboard saves."""
    with patch(
        "vauxhall.dashboard.app.save_user_config",
        side_effect=[user_config_path(DASHBOARD_FILE), OSError("read-only")],
    ):
        result = dashboard.save_settings({"mqtt": {"host": "b"}}, update_hooks=True)

    assert result["ok"] is True
    assert result["hooks_updated"] is False
    assert result["hooks_error"] == "read-only"


def test_ipc_get_settings_returns_json() -> None:
    """The bridge returns the settings description as JSON."""
    described = json.loads(DashboardIPC().get_settings())

    assert len(described["fields"]) == 13


def test_ipc_get_settings_reports_malformed_file() -> None:
    """A malformed dashboard file is reported instead of raising."""
    write_user_file(DASHBOARD_FILE, '{"mqtt": 5}')

    described = json.loads(DashboardIPC().get_settings())

    assert "mqtt must be an object" in described["error"]


def test_ipc_save_settings_forwards_request() -> None:
    """A valid request is passed to the save callback and its result returned."""
    callback = MagicMock(return_value={"ok": True})
    ipc = DashboardIPC(on_save_settings=callback)

    response = ipc.save_settings(
        json.dumps({"changes": {"mqtt": {"port": 1884}}, "update_hooks": True})
    )

    assert json.loads(response) == {"ok": True}
    callback.assert_called_once_with({"mqtt": {"port": 1884}}, update_hooks=True)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"changes": {"mqtt": 5}}',
        '{"changes": {}, "update_hooks": "yes"}',
    ],
)
def test_ipc_save_settings_rejects_invalid_requests(payload: str) -> None:
    """Malformed requests are rejected without calling the save callback."""
    callback = MagicMock()
    ipc = DashboardIPC(on_save_settings=callback)

    assert json.loads(ipc.save_settings(payload))["ok"] is False
    callback.assert_not_called()


def test_ipc_save_settings_reports_callback_failure() -> None:
    """An unexpected save failure is reported instead of raising."""
    ipc = DashboardIPC(on_save_settings=MagicMock(side_effect=RuntimeError("boom")))

    response = json.loads(ipc.save_settings('{"changes": {}}'))

    assert response == {"ok": False, "error": "Settings could not be saved"}
