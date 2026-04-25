# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for Vauxhall Dashboard components."""

import json
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

# Mock dependencies that might not be available or should be isolated
sys_modules_patch = patch.dict(
    "sys.modules",
    {
        "pyperclip": MagicMock(),
        "paho": MagicMock(),
        "paho.mqtt": MagicMock(),
        "paho.mqtt.client": MagicMock(),
    },
)
sys_modules_patch.start()

from vauxhall.dashboard.ipc import DashboardIPC  # noqa: E402
from vauxhall.dashboard.mqtt_client import DashboardSubscriber  # noqa: E402


class TestDashboardComponents(unittest.TestCase):
    """Tests for IPC and Subscriber components."""

    def test_ipc_copy_to_clipboard(self) -> None:
        """Test that the IPC bridge correctly calls pyperclip."""
        ipc = DashboardIPC()
        with patch("vauxhall.dashboard.ipc.pyperclip.copy") as mock_copy:
            result = ipc.copy_to_clipboard("test text")
            mock_copy.assert_called_once_with("test text")
            assert result

    def test_ipc_copy_to_clipboard_error(self) -> None:
        """Test that clipboard errors are handled gracefully."""
        ipc = DashboardIPC()
        with patch(
            "vauxhall.dashboard.ipc.pyperclip.copy", side_effect=Exception("error")
        ):
            result = ipc.copy_to_clipboard("test text")
            assert not result

    def test_subscriber_on_message(self) -> None:
        """Test that the subscriber correctly forwards MQTT messages to the callback."""
        callback = MagicMock()
        subscriber = DashboardSubscriber(callback, MagicMock())

        # Create a mock message
        msg: Any = MagicMock()
        data = {
            "agent": "Gemini",
            "workspace": "/home/user/project",
            "state": "Running",
        }
        msg.payload = json.dumps(data).encode()

        # Call the private method directly for testing
        subscriber._on_message(None, None, msg)

        callback.assert_called_once_with(data)

    def test_subscriber_on_message_invalid_json(self) -> None:
        """Test that invalid JSON messages are ignored by the subscriber."""
        callback = MagicMock()
        subscriber = DashboardSubscriber(callback, MagicMock())

        # Create a mock message with invalid JSON
        msg: Any = MagicMock()
        msg.payload = b"invalid json"

        # Should not raise exception, but also not call callback
        subscriber._on_message(None, None, msg)

        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
