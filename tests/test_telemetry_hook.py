"""Tests for Gemini telemetry hook."""

import io
import json
from unittest.mock import patch

from vauxhall.hooks.gemini.telemetry_hook import main


def test_notification_tool_permission() -> None:
    """Verify that a ToolPermission notification sets the 'Waiting for Input' state."""
    hook_data = {
        "hook_event_name": "Notification",
        "notification_type": "ToolPermission",
        "message": "Confirm deletion?",
        "details": {"tool_name": "run_shell_command"},
        "cwd": "/workspace",
    }

    with (
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as MockClient,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = MockClient.return_value
        main()

        mock_instance.send.assert_called_once_with(
            agent="Gemini",
            workspace="/workspace",
            state="Waiting for Input",
            prompt="Confirm deletion?",
            tool="run_shell_command",
        )


def test_ask_user_tool() -> None:
    """Verify that an ask_user tool call sets the state to 'Waiting for Input'."""
    hook_data = {
        "hook_event_name": "BeforeTool",
        "tool_name": "ask_user",
        "tool_input": {"questions": [{"question": "Continue?"}]},
        "cwd": "/workspace",
    }

    with (
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as MockClient,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = MockClient.return_value
        main()

        mock_instance.send.assert_called_once_with(
            agent="Gemini",
            workspace="/workspace",
            state="Waiting for Input",
            prompt="Continue?",
        )
