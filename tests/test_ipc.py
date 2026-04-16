# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the IPC bridge."""

from unittest.mock import MagicMock, patch

from vauxhall.dashboard.ipc import DashboardIPC


def test_ipc_ping() -> None:
    """Verify that the ping method returns True."""
    ipc = DashboardIPC()
    assert ipc.ping() is True


def test_ipc_set_ready() -> None:
    """Verify that set_ready triggers the callback and updates state."""
    callback = MagicMock()
    ipc = DashboardIPC(on_ready_callback=callback)

    assert ipc.is_ready is False
    assert ipc.set_ready() is True
    assert ipc.is_ready is True
    callback.assert_called_once()


def test_ipc_get_stale_threshold() -> None:
    """Verify that get_stale_threshold returns value from settings."""
    from vauxhall.config import settings

    ipc = DashboardIPC()
    assert ipc.get_stale_threshold() == settings.dashboard.stale_threshold


@patch("pyperclip.copy")
def test_ipc_copy_to_clipboard(mock_copy: MagicMock) -> None:
    """Verify that copy_to_clipboard calls pyperclip."""
    ipc = DashboardIPC()
    assert ipc.copy_to_clipboard("test text") is True
    mock_copy.assert_called_once_with("test text")


@patch("pyperclip.copy")
def test_ipc_copy_to_clipboard_error(mock_copy: MagicMock) -> None:
    """Verify that copy_to_clipboard handles errors gracefully."""
    mock_copy.side_effect = Exception("clipboard error")
    ipc = DashboardIPC()
    assert ipc.copy_to_clipboard("test text") is False
