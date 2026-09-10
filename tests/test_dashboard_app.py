# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for Vauxhall Dashboard components."""

import json
import unittest
from copy import deepcopy
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

from vauxhall.dashboard.app import DashboardApp  # noqa: E402
from vauxhall.dashboard.ipc import DashboardIPC  # noqa: E402
from vauxhall.dashboard.mqtt_client import DashboardSubscriber  # noqa: E402


class TestDashboardComponents(unittest.TestCase):
    """Tests for IPC and Subscriber components."""

    def valid_telemetry(self) -> dict[str, Any]:
        """Return one valid schema-v1 dashboard update."""
        return {
            "schema_version": 1,
            "agent": "TestAgent",
            "workspace": "/path",
            "session_id": "native:session-1",
            "state": "Acting",
            "details": {},
        }

    def setUp(self) -> None:
        """Set up the test environment."""
        self.mock_app = MagicMock()
        self.dashboard = DashboardApp(self.mock_app)
        self.dashboard.window = MagicMock()

    def test_on_telemetry_missing_fields(self) -> None:
        """Verify that telemetry missing required fields is dropped."""
        self.dashboard.ipc.is_ready = True

        # Missing workspace
        missing_workspace = self.valid_telemetry()
        del missing_workspace["workspace"]
        self.dashboard.on_telemetry(missing_workspace)
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 0

        # Missing state
        missing_state = self.valid_telemetry()
        del missing_state["state"]
        self.dashboard.on_telemetry(missing_state)
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 0

    def test_on_telemetry_queuing(self) -> None:
        """Verify that telemetry queued when IPC is not ready and flushed on drain."""
        self.dashboard.ipc.is_ready = False

        valid_data = self.valid_telemetry()
        self.dashboard.on_telemetry(valid_data)

        # Should be queued, not invoked
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 1
        assert self.dashboard.pending_updates[0] == valid_data

        # Drain queue
        self.dashboard.drain_queue()
        self.dashboard.window.invoke.assert_called_once_with("agent-update", valid_data)
        assert len(self.dashboard.pending_updates) == 0

    def test_on_telemetry_forwards_valid_data_immediately(self) -> None:
        """Verify that valid telemetry reaches ready frontend IPC immediately."""
        self.dashboard.ipc.is_ready = True
        valid_data = self.valid_telemetry()
        expected_data = deepcopy(valid_data)

        self.dashboard.on_telemetry(valid_data)

        self.dashboard.window.invoke.assert_called_once_with(
            "agent-update", expected_data
        )
        forwarded_data = self.dashboard.window.invoke.call_args.args[1]
        assert forwarded_data == expected_data
        assert forwarded_data is not expected_data
        assert self.dashboard.pending_updates == []

    def test_on_telemetry_rejects_unversioned_and_unsupported_messages(self) -> None:
        """Only supported schema-v1 telemetry may reach dashboard state."""
        self.dashboard.ipc.is_ready = False
        unversioned = self.valid_telemetry()
        del unversioned["schema_version"]
        unsupported = {**self.valid_telemetry(), "schema_version": 2}

        with self.assertLogs("vauxhall.dashboard.app", level="WARNING") as logs:
            self.dashboard.on_telemetry(unversioned)
            self.dashboard.on_telemetry(unsupported)

        assert self.dashboard.pending_updates == []
        self.dashboard.window.invoke.assert_not_called()
        assert "schema_version is required" in logs.output[0]
        assert "unsupported schema_version; expected 1" in logs.output[1]

    def test_on_telemetry_rejection_log_does_not_include_payload(self) -> None:
        """Protocol warnings must not leak any raw payload content."""
        schema_sentinel = 2718281828
        invalid = {
            **self.valid_telemetry(),
            "schema_version": schema_sentinel,
            "agent": "sentinel-agent",
            "workspace": "sentinel-workspace",
            "session_id": "sentinel-session",
            "state": "sentinel-state",
            "details": {
                "prompt": "sentinel-prompt",
                "cmd": "sentinel-command",
            },
            "extra": "sentinel-extra",
        }

        with self.assertLogs("vauxhall.dashboard.app", level="WARNING") as logs:
            self.dashboard.on_telemetry(invalid)

        assert logs.output == [
            (
                "WARNING:vauxhall.dashboard.app:Rejected telemetry: "
                "unsupported schema_version; expected 1"
            )
        ]
        for sentinel in (
            str(schema_sentinel),
            "sentinel-agent",
            "sentinel-workspace",
            "sentinel-session",
            "sentinel-state",
            "sentinel-prompt",
            "sentinel-command",
            "sentinel-extra",
        ):
            assert sentinel not in logs.output[0]

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
            "schema_version": 1,
            "agent": "Gemini",
            "workspace": "/home/user/project",
            "session_id": "native:session-1",
            "state": "Running",
            "details": {},
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
