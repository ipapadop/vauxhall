# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for Gemini telemetry hook."""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from vauxhall.hooks.gemini.telemetry_hook import main


def test_ignored_notification_outputs_valid_json() -> None:
    """An irrelevant notification still satisfies the Gemini hook protocol."""
    hook_data = {
        "session_id": "test-session",
        "transcript_path": "/workspace/transcript.json",
        "cwd": "/workspace",
        "hook_event_name": "Notification",
        "timestamp": "2026-09-04T12:00:00Z",
        "notification_type": "Info",
        "message": "Informational message",
    }

    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.gemini.telemetry_hook"],
        input=json.dumps(hook_data),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert completed.stderr == ""


def test_non_object_input_outputs_valid_json() -> None:
    """A valid JSON value with the wrong schema cannot break the hook protocol."""
    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.gemini.telemetry_hook"],
        input="[]",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert completed.stderr == ""


def test_gemini_hook_initializes_debug_logging_without_contaminating_stdout() -> None:
    """Configured hook logs must go to stderr and preserve protocol stdout."""
    hook_data = {
        "hook_event_name": "BeforeAgent",
        "session_id": "session-123",
        "cwd": "/workspace",
        "prompt": "Review the code",
    }
    environment = {
        **os.environ,
        "VAUXHALL_LOGGING_LEVEL": "DEBUG",
        "VAUXHALL_MQTT_HOST": "127.0.0.1",
        "VAUXHALL_MQTT_PORT": "1",
    }

    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.gemini.telemetry_hook"],
        input=json.dumps(hook_data),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert "Failed to connect telemetry client" in completed.stderr


def test_telemetry_initialization_failure_outputs_valid_json() -> None:
    """Telemetry setup failures remain invisible to the calling Gemini process."""
    hook_data = {
        "session_id": "test-session",
        "transcript_path": "/workspace/transcript.json",
        "cwd": "/workspace",
        "hook_event_name": "BeforeAgent",
        "timestamp": "2026-09-04T12:00:00Z",
        "prompt": "Review the code",
    }
    output = io.StringIO()

    with (
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=output),
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient",
            side_effect=RuntimeError,
        ),
    ):
        main()

    assert output.getvalue() == "{}\n"


def test_notification_tool_permission() -> None:
    """Verify that a ToolPermission notification sets the 'Waiting for Input' state."""
    hook_data = {
        "hook_event_name": "Notification",
        "notification_type": "ToolPermission",
        "message": "Confirm deletion?",
        "details": {"tool_name": "run_shell_command"},
        "session_id": "session-123",
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
            session_id="native:session-123",
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
        "session_id": "session-123",
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
            session_id="native:session-123",
            state="Waiting for Input",
            prompt="Continue?",
        )


def test_ask_question_tool() -> None:
    """Verify that an ask_question tool call sets the state to 'Waiting for Input'."""
    hook_data = {
        "hook_event_name": "BeforeTool",
        "tool_name": "ask_question",
        "tool_input": {"question": "What is next?"},
        "session_id": "session-123",
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
            session_id="native:session-123",
            state="Waiting for Input",
            prompt="What is next?",
        )


def test_after_model_tokens() -> None:
    """Verify that AfterModel extracts totalTokenCount."""
    hook_data = {
        "hook_event_name": "AfterModel",
        "llm_response": {"usageMetadata": {"totalTokenCount": 1234}},
        "session_id": "session-123",
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
            session_id="native:session-123",
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
        "session_id": "session-123",
        "cwd": str(workspace),
    }

    after_data = {
        "hook_event_name": "AfterTool",
        "tool_name": "ls",
        "session_id": "session-123",
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
            session_id="native:session-123",
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
        "session_id": "session-123",
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


def test_gemini_hook_skips_event_without_stable_session_identity() -> None:
    """Telemetry must be skipped when the hook has no stable identity source."""
    hook_data = {"hook_event_name": "BeforeAgent", "cwd": "/workspace"}
    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
        patch.dict("os.environ", {}, clear=True),
    ):
        main()

    mock_client_class.assert_not_called()
