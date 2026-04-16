# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for Gemini telemetry hook."""

import io
import json
import os
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


def test_ask_question_tool() -> None:
    """Verify that an ask_question tool call sets the state to 'Waiting for Input'."""
    hook_data = {
        "hook_event_name": "BeforeTool",
        "tool_name": "ask_question",
        "tool_input": {"question": "What is next?"},
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
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as MockClient,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        mock_instance = MockClient.return_value
        main()

        mock_instance.send.assert_called_once_with(
            agent="Gemini",
            workspace="/workspace",
            state="Thinking",
            status="Model replied",
            tokens=1234,
        )


def test_tool_duration_calculation() -> None:
    """Verify that duration is calculated between BeforeTool and AfterTool."""
    workspace = "/tmp/vauxhall-test-duration"
    os.makedirs(os.path.join(workspace, ".gemini"), exist_ok=True)
    
    before_data = {
        "hook_event_name": "BeforeTool",
        "tool_name": "ls",
        "cwd": workspace,
    }
    
    after_data = {
        "hook_event_name": "AfterTool",
        "tool_name": "ls",
        "cwd": workspace,
    }

    with (
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as MockClient,
        patch("sys.stdout", new=io.StringIO()),
        patch("time.time") as mock_time,
    ):
        mock_instance = MockClient.return_value
        
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
            workspace=workspace,
            state="Thinking",
            tool="ls",
            status="completed",
            duration=2.5,
        )
    
    # Cleanup
    import shutil
    shutil.rmtree(workspace)
