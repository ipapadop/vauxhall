# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the IPC bridge."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.ipc import DashboardIPC


def test_ipc_ping() -> None:
    """Verify that the ping method returns True."""
    ipc = DashboardIPC()
    assert ipc.ping() is True


def test_ipc_set_ready() -> None:
    """Verify that set_ready triggers its callback only on the first call."""
    callback = MagicMock()
    ipc = DashboardIPC(on_ready_callback=callback)

    assert ipc.is_ready is False
    assert ipc.set_ready() is True
    assert ipc.set_ready() is True
    assert ipc.is_ready is True
    callback.assert_called_once()


def test_ipc_get_stale_threshold() -> None:
    """Verify that get_stale_threshold returns value from settings."""
    ipc = DashboardIPC()
    assert ipc.get_stale_threshold() == settings.dashboard.stale_threshold


def test_ipc_get_max_active_agents() -> None:
    """Verify that get_max_active_agents returns value from settings."""
    ipc = DashboardIPC()
    assert ipc.get_max_active_agents() == settings.dashboard.max_active_agents


def test_ipc_copy_to_clipboard_calls_the_registered_callback() -> None:
    """A registered callback is called with the text to copy."""
    callback = MagicMock()
    ipc = DashboardIPC(on_copy=callback)

    assert ipc.copy_to_clipboard("test text") is True
    callback.assert_called_once_with("test text")


def test_ipc_copy_to_clipboard_does_not_log_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The copied workspace path never appears in the log.

    Args:
        caplog: Captures log records.
    """
    caplog.set_level(logging.DEBUG, logger="vauxhall.dashboard.ipc")
    callback = MagicMock(side_effect=[None, Exception("no clipboard")])
    ipc = DashboardIPC(on_copy=callback)

    assert ipc.copy_to_clipboard("/home/alice/secret-project") is True
    assert ipc.copy_to_clipboard("/home/alice/secret-project") is False
    assert "secret-project" not in caplog.text


def test_ipc_copy_to_clipboard_without_a_callback_returns_false() -> None:
    """Without a registered callback, copying reports failure."""
    assert DashboardIPC().copy_to_clipboard("test text") is False


def test_ipc_copy_to_clipboard_handles_callback_errors() -> None:
    """A callback that raises is reported as a failure, not propagated."""
    callback = MagicMock(side_effect=Exception("clipboard error"))
    ipc = DashboardIPC(on_copy=callback)

    assert ipc.copy_to_clipboard("test text") is False


def test_ipc_notify_calls_the_registered_callback() -> None:
    """A registered callback is called with the title and message."""
    callback = MagicMock()
    ipc = DashboardIPC(on_notify=callback)

    assert ipc.notify("Codex needs attention", "Prompt: continue?") is True
    callback.assert_called_once_with("Codex needs attention", "Prompt: continue?")


def test_ipc_notify_without_a_callback_returns_false() -> None:
    """Without a registered callback, notify reports failure."""
    ipc = DashboardIPC()
    assert ipc.notify("title", "message") is False


def test_ipc_notify_handles_callback_errors() -> None:
    """A callback that raises is reported as a failure, not propagated."""
    callback = MagicMock(side_effect=Exception("tray unavailable"))
    ipc = DashboardIPC(on_notify=callback)

    assert ipc.notify("title", "message") is False


def _install_request(path: object, agents: object) -> str:
    """Encode an install request.

    Args:
        path: The ``path`` value.
        agents: The ``agents`` value.

    Returns:
        The JSON payload.
    """
    return json.dumps({"path": path, "agents": agents})


def test_install_hooks_starts_the_install(tmp_path: Path) -> None:
    """A valid request reaches the callback with known, deduplicated agents."""
    callback = MagicMock(return_value={"ok": True})
    ipc = DashboardIPC(hook_install=MagicMock(install_hooks=callback))

    result = ipc.install_hooks(
        _install_request(str(tmp_path), ["claude", "codex", "claude"])
    )

    assert json.loads(result) == {"ok": True}
    callback.assert_called_once_with(tmp_path, ["claude", "codex"])


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ("not json", "Invalid install request"),
        (json.dumps({"agents": ["claude"]}), "Not an absolute path"),
        (_install_request("relative", ["claude"]), "Not an absolute path"),
        (_install_request(["/x"], ["claude"]), "Not an absolute path"),
        (
            _install_request(str(Path("/no/such/dir").absolute()), ["claude"]),
            "Not a directory",
        ),
        (_install_request("FILE", ["claude"]), "Not a directory"),
        (_install_request("DIR", []), "Choose at least one known agent"),
        (_install_request("DIR", ["vim"]), "Choose at least one known agent"),
        (_install_request("DIR", "claude"), "Choose at least one known agent"),
    ],
)
def test_install_hooks_rejects_bad_requests(
    tmp_path: Path, payload: str, error: str
) -> None:
    """Invalid paths and agents never start an install."""
    file = tmp_path / "file"
    file.write_text("")
    payload = payload.replace('"FILE"', json.dumps(str(file))).replace(
        '"DIR"', json.dumps(str(tmp_path))
    )
    callback = MagicMock()
    ipc = DashboardIPC(hook_install=MagicMock(install_hooks=callback))

    result = json.loads(ipc.install_hooks(payload))

    assert result["ok"] is False
    assert result["error"].startswith(error)
    callback.assert_not_called()


def test_install_hooks_without_callback(tmp_path: Path) -> None:
    """Without a backend nothing can be installed."""
    result = DashboardIPC().install_hooks(_install_request(str(tmp_path), ["claude"]))

    assert json.loads(result)["ok"] is False


def test_install_hooks_callback_error_is_reported(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing backend is logged and reported, not raised."""
    ipc = DashboardIPC(
        hook_install=MagicMock(install_hooks=MagicMock(side_effect=RuntimeError("x")))
    )

    with caplog.at_level(logging.ERROR):
        result = ipc.install_hooks(_install_request(str(tmp_path), ["claude"]))

    assert json.loads(result) == {"ok": False, "error": "The install could not start"}
    assert "Failed to start the hook install" in caplog.text


def test_select_install_directory_without_callback() -> None:
    """Without a backend no directory can be chosen."""
    assert json.loads(DashboardIPC().select_install_directory())["ok"] is False


def test_select_install_directory_returns_the_callback_result() -> None:
    """The backend's choice and detection pass through."""
    choice = {"ok": True, "path": "/w", "agents": []}
    ipc = DashboardIPC(
        hook_install=MagicMock(select_install_directory=MagicMock(return_value=choice))
    )

    assert json.loads(ipc.select_install_directory()) == choice


def test_select_install_directory_callback_error_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing picker is logged and reported, not raised."""
    ipc = DashboardIPC(
        hook_install=MagicMock(
            select_install_directory=MagicMock(side_effect=RuntimeError("x"))
        )
    )

    with caplog.at_level(logging.ERROR):
        result = json.loads(ipc.select_install_directory())

    assert result == {"ok": False, "error": "Could not choose a directory"}
    assert "Failed to choose an install directory" in caplog.text


def test_detect_agents_returns_detection(tmp_path: Path) -> None:
    """Detection reports the agents a directory uses."""
    (tmp_path / ".codex").mkdir()

    result = json.loads(DashboardIPC().detect_agents(str(tmp_path)))

    assert result["ok"] is True
    assert [entry["detected"] for entry in result["agents"]] == [False, True, False]


def test_detect_agents_rejects_an_unreadable_directory(unsearchable_dir: Path) -> None:
    """A directory that can't be checked is refused, not raised."""
    result = json.loads(DashboardIPC().detect_agents(str(unsearchable_dir)))

    assert result["ok"] is False
    assert result["error"].startswith("Not a directory")


@pytest.mark.parametrize(
    "url", ["https://github.com/ipapadop/vauxhall", "http://example.com/a?b=c"]
)
def test_ipc_open_url_opens_web_urls(url: str) -> None:
    """An http or https URL is handed to the browser.

    Args:
        url: The URL to open.
    """
    opened: list[str] = []
    ipc = DashboardIPC()
    ipc.open_browser = opened.append

    assert ipc.open_url(url) is True
    assert opened == [url]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ssh://host",
        "/home/user/project",
        "https:relative",
        "",
        "\x01http://host/x",
        "ht\ntp://host",
        " https://host",
        "https://host/a b",
        "https://host/\x7f",
    ],
)
def test_ipc_open_url_refuses_other_urls_without_logging_them(
    url: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Any page script can call the bridge, so only web URLs are opened.

    Args:
        url: The URL to refuse.
        caplog: Captures the warning.
    """
    opened: list[str] = []
    ipc = DashboardIPC()
    ipc.open_browser = opened.append

    with caplog.at_level(logging.DEBUG):
        assert ipc.open_url(url) is False

    assert opened == []
    assert "Refused to open a URL" in caplog.text
    assert not url or url not in caplog.text


def test_ipc_open_url_reports_a_browser_failure() -> None:
    """A browser that can't be started yields False instead of raising."""

    def fail(_url: str) -> None:
        message = "no browser"
        raise OSError(message)

    ipc = DashboardIPC()
    ipc.open_browser = fail

    assert ipc.open_url("https://github.com/ipapadop/vauxhall") is False
