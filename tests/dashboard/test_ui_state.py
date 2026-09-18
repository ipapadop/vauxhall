# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for remembered dashboard view preferences and window geometry."""

import json
import logging
from pathlib import Path
from threading import Event, Thread
from unittest.mock import MagicMock, patch

import pytest

from vauxhall.core.config_store import user_config_path, write_json_atomically
from vauxhall.dashboard.app import DashboardApp
from vauxhall.dashboard.config import UIConfig, dashboard_settings
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.ui_state import (
    STATE_FILE,
    clean_ui_state,
    load_ui_state,
    update_ui_state,
    visible_position,
    window_geometry,
)

pytestmark = pytest.mark.usefixtures("isolated_cwd")

SCREEN = {"x": 0, "y": 0, "width": 1920, "height": 1080}


@pytest.fixture(autouse=True)
def default_dashboard_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test with the default dashboard settings.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setattr(dashboard_settings, "dashboard", UIConfig())


def state_path() -> Path:
    """Return the per-user dashboard state file.

    Returns:
        The path of the state file.
    """
    return user_config_path(STATE_FILE)


def write_state(content: str | bytes) -> Path:
    """Write raw content to the dashboard state file.

    Args:
        content: The case's raw file content.

    Returns:
        The path written.
    """
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_load_without_file_returns_empty_state() -> None:
    """A missing state file means no saved preferences."""
    assert load_ui_state() == {}


@pytest.mark.parametrize("content", ["{", "[]", b"\xff"])
def test_load_ignores_corrupt_file(
    content: str | bytes, caplog: pytest.LogCaptureFixture
) -> None:
    """A corrupt or non-object state file falls back to defaults with a warning.

    Args:
        content: The case's raw file content.
        caplog: Pytest log capture fixture.
    """
    write_state(content)

    with caplog.at_level(logging.WARNING):
        assert load_ui_state() == {}

    assert "Ignoring" in caplog.text


def test_clean_drops_unknown_and_invalid_values() -> None:
    """Only known keys with valid values survive cleaning."""
    cleaned = clean_ui_state(
        {
            "theme": "blue",
            "sort": "tokens",
            "history_filter": "x" * 65,
            "search": "codex",
            "window": {
                "width": 100,
                "height": 800,
                "x": True,
                "y": 20,
                "maximized": "yes",
                "zoom": 2,
            },
        }
    )

    assert cleaned == {"sort": "tokens", "window": {"height": 800, "y": 20}}


@pytest.mark.parametrize("value", [["Error"], "", 5])
def test_clean_rejects_non_string_or_empty_preferences(value: object) -> None:
    """Sort and filter preferences must be short, non-empty strings.

    Args:
        value: The case's value.
    """
    assert clean_ui_state({"history_filter": value}) == {}


def test_window_size_limits_follow_configured_size_limits() -> None:
    """Saved window sizes accept the same range as the configured size."""
    assert clean_ui_state({"window": {"width": 320, "height": 16384}}) == {
        "window": {"width": 320, "height": 16384}
    }
    assert clean_ui_state({"window": {"width": 319, "height": 16385}}) == {}


def test_update_merges_valid_changes_and_keeps_saved_values() -> None:
    """Valid changes are merged; invalid ones leave the saved value in place."""
    write_state(json.dumps({"theme": "light", "sort": "name"}))

    state = update_ui_state({"sort": "status", "theme": "blue"})

    assert state == {"theme": "light", "sort": "status"}
    assert json.loads(state_path().read_text(encoding="utf-8")) == state


def test_update_creates_state_file() -> None:
    """The first save creates the configuration directory and file."""
    update_ui_state({"history_filter": "Error"})

    assert json.loads(state_path().read_text(encoding="utf-8")) == {
        "history_filter": "Error"
    }


def test_concurrent_updates_do_not_discard_each_other() -> None:
    """A second update waits for the first to finish, so both values are kept."""
    first_writing = Event()
    release_first = Event()

    def blocking_write(path: Path, data: dict[str, object]) -> None:
        """Hold the first write open so the second update overlaps it.

        Args:
            path: File the state is written to.
            data: The state being written.
        """
        if data.get("theme") == "light":
            first_writing.set()
            assert release_first.wait(5)
        write_json_atomically(path, data)

    with patch(
        "vauxhall.dashboard.ui_state.write_json_atomically", side_effect=blocking_write
    ):
        first = Thread(target=update_ui_state, args=({"theme": "light"},))
        first.start()
        assert first_writing.wait(5)
        second = Thread(target=update_ui_state, args=({"sort": "recent"},))
        second.start()
        second.join(0.2)
        assert second.is_alive()

        release_first.set()
        first.join(5)
        second.join(5)

    assert json.loads(state_path().read_text(encoding="utf-8")) == {
        "theme": "light",
        "sort": "recent",
    }


@pytest.mark.parametrize(
    ("window", "screens", "expected"),
    [
        ({"x": 50, "y": 60, "width": 800}, [SCREEN], (50, 60)),
        (
            {"x": 2000, "y": 100, "width": 800},
            [SCREEN, {"x": 1920, "y": 0, "width": 1280, "height": 1024}],
            (2000, 100),
        ),
        ({"x": 5000, "y": 60, "width": 800}, [SCREEN], None),
        ({"x": 50, "y": -50, "width": 800}, [SCREEN], None),
        ({"x": 50, "y": 1060, "width": 800}, [SCREEN], None),
        ({"x": 1870, "y": 60, "width": 800}, [SCREEN], None),
        ({"x": 50, "width": 800}, [SCREEN], None),
        ({"x": 50, "y": 60, "width": 800}, [], None),
    ],
)
def test_visible_position(
    window: dict[str, int],
    screens: list[dict[str, int]],
    expected: tuple[int, int] | None,
) -> None:
    """A position is restored only if the window's top edge is on a screen.

    Args:
        window: The case's window geometry.
        screens: The case's screen geometries.
        expected: The result the case expects.
    """
    assert visible_position(window, screens) == expected


def test_window_geometry_of_normal_window() -> None:
    """A normal window saves its current size and position."""
    window = MagicMock()
    window.is_maximized.return_value = False
    window.get_size.return_value = {"width": 1000, "height": 750}
    window.get_position.return_value = {"x": 10, "y": 20}

    assert window_geometry(window, {"width": 900}) == {
        "width": 1000,
        "height": 750,
        "x": 10,
        "y": 20,
        "maximized": False,
    }


def test_window_geometry_of_maximized_window_keeps_normal_size() -> None:
    """A maximized window keeps the previously saved normal size and position."""
    window = MagicMock()
    window.is_maximized.return_value = True
    previous = {"width": 900, "height": 700, "x": 5, "y": 6}

    assert window_geometry(window, previous) == {**previous, "maximized": True}
    window.get_size.assert_not_called()


def test_ipc_get_ui_state_returns_only_frontend_preferences() -> None:
    """The bridge returns preferences but not window geometry."""
    write_state(json.dumps({"theme": "light", "window": {"width": 900}}))

    assert json.loads(DashboardIPC().get_ui_state()) == {"theme": "light"}


def test_ipc_save_ui_state_ignores_window_and_unknown_keys() -> None:
    """The frontend cannot change window geometry or add unknown keys."""
    write_state(json.dumps({"window": {"width": 900}}))

    assert DashboardIPC().save_ui_state(
        json.dumps({"sort": "recent", "window": {"width": 2000}, "search": "codex"})
    )

    assert json.loads(state_path().read_text(encoding="utf-8")) == {
        "window": {"width": 900},
        "sort": "recent",
    }


@pytest.mark.parametrize("payload", ["not json", "[]"])
def test_ipc_save_ui_state_rejects_invalid_payload(payload: str) -> None:
    """Malformed requests are rejected without writing.

    Args:
        payload: The case's payload.
    """
    assert DashboardIPC().save_ui_state(payload) is False
    assert not state_path().exists()


def test_ipc_save_ui_state_reports_write_failure() -> None:
    """A state file that cannot be written is reported as not saved."""
    with patch(
        "vauxhall.dashboard.ipc.update_ui_state", side_effect=OSError("read-only")
    ):
        assert DashboardIPC().save_ui_state('{"theme": "dark"}') is False


def run_dashboard(app: MagicMock) -> MagicMock:
    """Run the dashboard until its UI loop exits and return the subscriber type.

    Args:
        app: Mocked Pyloid application the dashboard runs on.

    Returns:
        The patched ``DashboardSubscriber`` type.
    """
    app.run.side_effect = SystemExit(0)
    with (
        patch("vauxhall.dashboard.app.pyloid_serve", return_value="http://localhost"),
        patch("vauxhall.dashboard.app.DashboardSubscriber") as subscriber_type,
        pytest.raises(SystemExit),
    ):
        DashboardApp(app).run()
    return subscriber_type


def screen_app() -> MagicMock:
    """Return a Pyloid app mock with one connected screen.

    Returns:
        The application mock.
    """
    app = MagicMock()
    monitor = MagicMock()
    monitor.available_geometry.return_value = SCREEN
    app.get_all_monitors.return_value = [monitor]
    return app


def test_run_restores_and_saves_window_geometry() -> None:
    """Saved size, position, and maximized state are restored and updated on exit."""
    write_state(
        json.dumps(
            {
                "theme": "light",
                "window": {
                    "width": 900,
                    "height": 700,
                    "x": 50,
                    "y": 60,
                    "maximized": True,
                },
            }
        )
    )
    app = screen_app()
    window = app.create_window.return_value
    window.is_maximized.return_value = False
    window.get_size.return_value = {"width": 1000, "height": 750}
    window.get_position.return_value = {"x": 10, "y": 20}

    run_dashboard(app)

    assert app.create_window.call_args.kwargs["width"] == 900
    assert app.create_window.call_args.kwargs["height"] == 700
    window.set_position.assert_called_once_with(50, 60)
    window.maximize.assert_called_once_with()
    assert json.loads(state_path().read_text(encoding="utf-8")) == {
        "theme": "light",
        "window": {"width": 1000, "height": 750, "x": 10, "y": 20, "maximized": False},
    }


def test_run_without_saved_state_uses_configured_size() -> None:
    """Without saved state, the configured size and default position are used."""
    app = MagicMock()
    window = app.create_window.return_value
    window.is_maximized.return_value = False
    window.get_size.return_value = {"width": 1000, "height": 800}
    window.get_position.return_value = {"x": 200, "y": 200}

    run_dashboard(app)

    assert app.create_window.call_args.kwargs["width"] == 1000
    assert app.create_window.call_args.kwargs["height"] == 800
    app.get_all_monitors.assert_not_called()
    window.set_position.assert_not_called()
    window.maximize.assert_not_called()


def test_run_skips_off_screen_position() -> None:
    """A saved position on a disconnected screen is not restored."""
    write_state(json.dumps({"window": {"width": 900, "x": 5000, "y": 60}}))
    app = screen_app()
    app.create_window.return_value.is_maximized.return_value = True

    run_dashboard(app)

    app.create_window.return_value.set_position.assert_not_called()


def test_window_state_save_failure_does_not_stop_shutdown() -> None:
    """A failure to save window geometry is logged and shutdown continues."""
    app = MagicMock()
    app.create_window.return_value.is_maximized.side_effect = RuntimeError("gone")

    subscriber_type = run_dashboard(app)

    subscriber_type.return_value.stop.assert_called_once_with()
    assert not state_path().exists()
