# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
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

import pytest

from vauxhall.hooks.gemini.telemetry_hook import _classify_tool_response, main


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


@pytest.mark.parametrize(
    ("environment_value", "file_payload", "expected_source", "expected_value"),
    [
        ("invalid", None, "VAUXHALL_MQTT_PORT", "'invalid'"),
        (None, {"mqtt": []}, "vauxhall_hooks.json", "[]"),
    ],
)
def test_gemini_hook_reports_invalid_configuration_without_breaking_protocol(
    tmp_path: Path,
    environment_value: str | None,
    file_payload: object | None,
    expected_source: str,
    expected_value: str,
) -> None:
    """Invalid hook configuration remains actionable without corrupting stdout."""
    if file_payload is not None:
        (tmp_path / "vauxhall_hooks.json").write_text(json.dumps(file_payload))
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VAUXHALL_")
    }
    if environment_value is not None:
        environment["VAUXHALL_MQTT_PORT"] = environment_value
    project_root = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (project_root, environment.get("PYTHONPATH")))
    )

    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.gemini.telemetry_hook"],
        input="{}",
        text=True,
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert expected_source in completed.stderr
    assert expected_value in completed.stderr
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize(
    ("response", "state", "status", "error"),
    [
        (
            {"llmContent": "secret", "returnDisplay": "secret"},
            "Thinking",
            "completed",
            None,
        ),
        (
            {"error": {"message": "secret"}},
            "Error",
            "failed",
            "Tool reported an error",
        ),
        (
            {"error": {"code": "CANCELLED", "message": "secret"}},
            "Idle",
            "cancelled",
            None,
        ),
        (None, "Thinking", "result unavailable", None),
        ([], "Thinking", "result unavailable", None),
    ],
)
def test_gemini_after_tool_outcomes(
    response: object, state: str, status: str, error: str | None
) -> None:
    """AfterTool responses must map to truthful dashboard outcomes."""
    assert _classify_tool_response(response) == (state, status, error)


def test_gemini_after_tool_does_not_publish_response_content(tmp_path: Path) -> None:
    """AfterTool publishes only normalized outcome fields, never result content."""
    workspace = tmp_path / "workspace"
    (workspace / ".gemini").mkdir(parents=True)
    hook_data = {
        "hook_event_name": "AfterTool",
        "tool_name": "run_shell_command",
        "tool_response": {"error": {"message": "secret"}},
        "session_id": "session-123",
        "cwd": str(workspace),
    }

    with (
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        client = client_class.return_value
        client.__enter__.return_value = client
        main()

    assert client.send.call_args.kwargs == {
        "agent": "Gemini",
        "workspace": str(workspace),
        "state": "Error",
        "tool": "run_shell_command",
        "status": "failed",
        "error": "Tool reported an error",
        "session_id": "native:session-123",
    }
    assert "secret" not in json.dumps(client.send.call_args.kwargs)


@pytest.mark.parametrize(
    ("reason", "status"),
    [
        ("exit", "session exited"),
        ("clear", "session cleared"),
        ("logout", "logged out"),
        ("prompt_input_exit", "input closed"),
        ("other", "session ended"),
        (None, "session ended"),
        (123, "session ended"),
        ([], "session ended"),
    ],
)
def test_gemini_session_end_maps_documented_reasons(
    reason: object, status: str
) -> None:
    """SessionEnd must emit only normalized statuses for known CLI reasons."""
    hook_data = {
        "hook_event_name": "SessionEnd",
        "session_id": "session-123",
        "reason": reason,
        "cwd": "/workspace",
    }

    with (
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as client_class,
        patch("sys.stdin", io.StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=io.StringIO()),
    ):
        client = client_class.return_value
        client.__enter__.return_value = client
        main()

    client.send.assert_called_once_with(
        agent="Gemini",
        workspace="/workspace",
        state="Idle",
        status=status,
        session_id="native:session-123",
    )


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
        "tool_response": {"returnDisplay": "directory listing"},
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


def test_tool_durations_are_isolated_by_session_and_tool_call(tmp_path: Path) -> None:
    """Concurrent Gemini tool calls must retain their own start times."""
    workspace = tmp_path / "vauxhall-concurrent-tools"
    (workspace / ".gemini").mkdir(parents=True)
    events = [
        {
            "hook_event_name": "BeforeTool",
            "tool_name": "alpha",
            "session_id": "session-one",
            "tool_call_id": "call-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "BeforeTool",
            "tool_name": "beta",
            "session_id": "session-one",
            "tool_call_id": "call-two",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "BeforeTool",
            "tool_name": "gamma",
            "session_id": "session-two",
            "tool_call_id": "call-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "AfterTool",
            "tool_name": "alpha",
            "session_id": "session-one",
            "tool_call_id": "call-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "AfterTool",
            "tool_name": "beta",
            "session_id": "session-one",
            "tool_call_id": "call-two",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "AfterTool",
            "tool_name": "gamma",
            "session_id": "session-two",
            "tool_call_id": "call-one",
            "cwd": str(workspace),
        },
    ]

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdout", new=io.StringIO()),
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.time.time",
            side_effect=[1000.0, 1001.0, 1002.0, 1003.0, 1005.0, 1008.0],
        ),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
        for event in events:
            with patch("sys.stdin", io.StringIO(json.dumps(event))):
                main()

    completed = {
        call.kwargs["tool"]: call.kwargs.get("duration")
        for call in mock_instance.send.call_args_list
        if call.kwargs["state"] == "Thinking"
    }
    assert completed == {"alpha": 3.0, "beta": 4.0, "gamma": 6.0}


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
