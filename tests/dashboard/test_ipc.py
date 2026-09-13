# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the IPC bridge."""

from unittest.mock import MagicMock, patch

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


@patch("vauxhall.dashboard.ipc.pyperclip.copy")
def test_ipc_copy_to_clipboard(mock_copy: MagicMock) -> None:
    """Verify that copy_to_clipboard calls pyperclip."""
    ipc = DashboardIPC()
    assert ipc.copy_to_clipboard("test text") is True
    mock_copy.assert_called_once_with("test text")


@patch("vauxhall.dashboard.ipc.pyperclip.copy")
def test_ipc_copy_to_clipboard_error(mock_copy: MagicMock) -> None:
    """Verify that copy_to_clipboard handles errors gracefully."""
    mock_copy.side_effect = Exception("clipboard error")
    ipc = DashboardIPC()
    assert ipc.copy_to_clipboard("test text") is False
