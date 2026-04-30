# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for Gemini telemetry hook."""

import io
import json
import shutil
from pathlib import Path
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
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
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
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
        main()

        mock_instance.send.assert_called_once_with(
            agent="Gemini",
            workspace="/workspace",
            state="Waiting for Input",
            prompt="Continue?",
        )


def test_ask_question_tool() -> None:
    """Verify that an ask_question tool call sets the state to 'Waiting for Input'."""
    hook_data = {
        "hook_event_name": "BeforeTool",
        "tool_name": "ask_question",
        "tool_input": {"question": "What is next?"},
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
        main()

        mock_instance.send.assert_called_once_with(
            agent="Gemini",
            workspace="/workspace",
            state="Waiting for Input",
            prompt="What is next?",
        )


def test_after_model_tokens() -> None:
    """Verify that AfterModel extracts totalTokenCount."""
    hook_data = {
        "hook_event_name": "AfterModel",
        "llm_response": {"usageMetadata": {"totalTokenCount": 1234}},
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
        main()

        mock_instance.send.assert_called_once_with(
            agent="Gemini",
            workspace="/workspace",
            state="Thinking",
            status="Model replied",
            tokens=1234,
        )


def test_tool_duration_calculation(tmp_path: Path) -> None:
    """Verify that duration is calculated between BeforeTool and AfterTool."""
    workspace = tmp_path / "vauxhall-test-duration"
    (workspace / ".gemini").mkdir(parents=True, exist_ok=True)

    before_data = {
        "hook_event_name": "BeforeTool",
        "tool_name": "ls",
        "cwd": str(workspace),
    }

    after_data = {
        "hook_event_name": "AfterTool",
        "tool_name": "ls",
        "cwd": str(workspace),
    }

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdout", new=io.StringIO()),
        patch("time.time") as mock_time,
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance

        # 1. BeforeTool
        mock_time.return_value = 1000.0
        with patch("sys.stdin", io.StringIO(json.dumps(before_data))):
            main()

        # 2. AfterTool
        mock_time.return_value = 1002.5
        with patch("sys.stdin", io.StringIO(json.dumps(after_data))):
            main()

        # Check AfterTool call (last call)
        mock_instance.send.assert_called_with(
            agent="Gemini",
            workspace=str(workspace),
            state="Thinking",
            tool="ls",
            status="completed",
            duration=2.5,
        )

    # Cleanup
    shutil.rmtree(workspace)


def test_unknown_tool_before_tool() -> None:
    """Verify that an unknown tool in BeforeTool does not send 'tool' key."""
    hook_data = {
        "hook_event_name": "BeforeTool",
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
        main()

        # Should NOT have 'tool' key
        mock_instance.send.assert_called_once()
        kwargs = mock_instance.send.call_args.kwargs
        assert "tool" not in kwargs
        assert kwargs["state"] == "Acting"
