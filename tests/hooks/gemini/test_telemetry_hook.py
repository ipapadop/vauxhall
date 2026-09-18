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
from unittest.mock import MagicMock, patch

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
    project_root = str(Path(__file__).resolve().parents[3])
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
        "details": {
            "type": "mcp",
            "title": "Confirm MCP Tool Execution",
            "serverName": "filesystem",
            "toolName": "delete_file",
        },
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
            tool="delete_file",
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


def test_after_model_tokens() -> None:
    """Verify that AfterModel extracts totalTokenCount."""
    hook_data = {
        "hook_event_name": "AfterModel",
        "llm_response": {
            "candidates": [{"content": {"parts": []}, "finishReason": "STOP"}],
            "usageMetadata": {"totalTokenCount": 1234},
        },
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


def test_tool_durations_are_isolated_by_session_and_tool(tmp_path: Path) -> None:
    """Concurrent Gemini tool calls must retain their own start times."""
    workspace = tmp_path / "vauxhall-concurrent-tools"
    (workspace / ".gemini").mkdir(parents=True)
    events = [
        {
            "hook_event_name": "BeforeTool",
            "tool_name": "alpha",
            "session_id": "session-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "BeforeTool",
            "tool_name": "beta",
            "session_id": "session-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "BeforeTool",
            "tool_name": "gamma",
            "session_id": "session-two",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "AfterTool",
            "tool_name": "alpha",
            "session_id": "session-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "AfterTool",
            "tool_name": "beta",
            "session_id": "session-one",
            "cwd": str(workspace),
        },
        {
            "hook_event_name": "AfterTool",
            "tool_name": "gamma",
            "session_id": "session-two",
            "cwd": str(workspace),
        },
    ]

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdout", new=io.StringIO()),
        patch(
            "vauxhall.hooks.common.time.time",
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


def test_tool_durations_are_isolated_by_tool_input(
    tmp_path: Path,
) -> None:
    """Concurrent calls without IDs must not share one per-workspace start time."""
    workspace = tmp_path / "no-gemini-directory"

    def event(hook: str, command: str) -> dict:
        """Build an ID-less shell tool event for the given command.

        Args:
            hook: Name of the hook event to build.
            command: Shell command carried in the tool input.

        Returns:
            The event.
        """
        return {
            "hook_event_name": hook,
            "tool_name": "run_shell_command",
            "tool_input": {"command": command},
            "session_id": "session-one",
            "cwd": str(workspace),
        }

    events = [
        event("BeforeTool", "sleep 5"),
        event("BeforeTool", "ls"),
        event("AfterTool", "ls"),
        event("AfterTool", "sleep 5"),
    ]

    with (
        patch(
            "vauxhall.hooks.gemini.telemetry_hook.TelemetryClient"
        ) as mock_client_class,
        patch("sys.stdout", new=io.StringIO()),
        patch(
            "vauxhall.hooks.common.time.time",
            side_effect=[1000.0, 1004.0, 1005.0, 1010.0],
        ),
    ):
        mock_instance = mock_client_class.return_value
        mock_instance.__enter__.return_value = mock_instance
        for item in events:
            with patch("sys.stdin", io.StringIO(json.dumps(item))):
                main()

    durations = [
        call.kwargs.get("duration")
        for call in mock_instance.send.call_args_list
        if call.kwargs["state"] == "Thinking"
    ]
    assert durations == [1.0, 10.0]
    assert not workspace.exists()


@pytest.mark.parametrize(
    "hook_data",
    [
        {"hook_event_name": "BeforeTool", "session_id": "s", "tool_input": []},
        {"hook_event_name": "AfterModel", "session_id": "s", "llm_response": "x"},
        {
            "hook_event_name": "Notification",
            "session_id": "s",
            "notification_type": "ToolPermission",
            "details": "not-an-object",
        },
        {"hook_event_name": "BeforeTool", "session_id": "s", "cwd": ["not-a-path"]},
    ],
)
def test_malformed_nested_input_outputs_valid_json(hook_data: dict) -> None:
    """Malformed nested hook fields cannot break the Gemini stdout protocol."""
    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.gemini.telemetry_hook"],
        input=json.dumps(hook_data),
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "VAUXHALL_MQTT_HOST": "127.0.0.1",
            "VAUXHALL_MQTT_PORT": "1",
        },
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"


def _run(*events: dict) -> MagicMock:
    """Run the hook for each event and return the mocked telemetry client."""
    with (
        patch("vauxhall.hooks.gemini.telemetry_hook.TelemetryClient") as client_class,
        patch("sys.stdout", new=io.StringIO()),
    ):
        client = client_class.return_value
        client.__enter__.return_value = client
        for event in events:
            with patch("sys.stdin", io.StringIO(json.dumps(event))):
                main()
    return client


def test_gemini_publishes_model_text_before_turn_ends(tmp_path: Path) -> None:
    """Streaming model chunks form one message at each model response end."""
    base = {
        "hook_event_name": "AfterModel",
        "session_id": "session-123",
        "cwd": "/workspace",
    }
    first = {
        **base,
        "llm_response": {"candidates": [{"content": {"parts": ["Working "]}}]},
    }
    last = {
        **base,
        "llm_response": {
            "candidates": [
                {"content": {"parts": ["through it."]}, "finishReason": "STOP"}
            ]
        },
    }

    with patch("vauxhall.hooks.common.tempfile.gettempdir", return_value=str(tmp_path)):
        client = _run(first, last)

    client.send.assert_called_once_with(
        agent="Gemini",
        workspace="/workspace",
        session_id="native:session-123",
        state="Thinking",
        status="Model replied",
        message="Working through it.",
    )


@pytest.mark.parametrize(
    ("hook_data", "expected"),
    [
        (
            {"hook_event_name": "SessionStart", "source": "startup"},
            {"state": "Idle", "status": "Session started"},
        ),
        (
            {"hook_event_name": "SessionStart", "source": "resume"},
            {"state": "Idle", "status": "Session resumed"},
        ),
        (
            {"hook_event_name": "SessionStart", "source": ["clear"]},
            {"state": "Idle", "status": "Session started"},
        ),
        (
            {"hook_event_name": "PreCompress", "trigger": "auto"},
            {"state": "Thinking", "status": "Compacting context"},
        ),
        (
            {"hook_event_name": "PreCompress", "trigger": "manual"},
            {"state": "Idle", "status": "Compacting context"},
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "ToolPermission",
                "message": "Allow execution?",
                "details": {
                    "type": "exec",
                    "title": "Confirm Shell Command",
                    "command": "rm -rf build",
                    "rootCommand": "rm",
                },
            },
            {"state": "Waiting for Input", "prompt": "Allow execution?"},
        ),
    ],
)
def test_gemini_lifecycle_events_publish_dashboard_states(
    hook_data: dict, expected: dict
) -> None:
    """Lifecycle events and notifications must publish normalized states."""
    client = _run({**hook_data, "session_id": "session-123", "cwd": "/workspace"})

    client.send.assert_called_once_with(
        agent="Gemini",
        workspace="/workspace",
        session_id="native:session-123",
        **expected,
    )


@pytest.mark.parametrize(
    "hook_data",
    [
        {"tool_name": "run_shell_command"},
        {"hook_event_name": "BeforeModel"},
    ]
    + [
        {"hook_event_name": "AfterModel", "llm_response": llm_response}
        for llm_response in [
            {"candidates": [{"content": {"role": "model", "parts": ["partial"]}}]},
            {"candidates": [{"content": {"parts": ["partial"]}, "finishReason": ""}]},
            {"candidates": [{"finishReason": "FINISH_REASON_UNSPECIFIED"}]},
            {
                "candidates": ["not-a-candidate"],
                "usageMetadata": {"totalTokenCount": 9},
            },
            {"candidates": "not-a-list"},
            {"usageMetadata": {"totalTokenCount": 12}},
            "not-an-object",
        ]
    ],
)
def test_gemini_ignores_events_without_dashboard_state(hook_data: dict) -> None:
    """Unnamed, unregistered, and non-final streaming events must not publish."""
    client = _run({**hook_data, "session_id": "session-123", "cwd": "/workspace"})

    client.send.assert_not_called()


def test_identical_concurrent_tool_calls_each_report_a_duration(tmp_path: Path) -> None:
    """Identical overlapping calls must not share or overwrite a start time."""
    event = {
        "tool_name": "run_shell_command",
        "tool_input": {"command": "make test"},
        "tool_response": {"llmContent": "ok"},
        "session_id": "session-one",
        "cwd": "/workspace",
    }

    with (
        patch("vauxhall.hooks.common.tempfile.gettempdir", return_value=str(tmp_path)),
        patch(
            "vauxhall.hooks.common.time.time",
            side_effect=[1000.0, 1002.0, 1005.0, 1009.0],
        ),
    ):
        client = _run(
            *(
                {**event, "hook_event_name": hook}
                for hook in ("BeforeTool", "BeforeTool", "AfterTool", "AfterTool")
            )
        )

    durations = [
        call.kwargs.get("duration")
        for call in client.send.call_args_list
        if call.kwargs["state"] == "Thinking"
    ]
    assert durations == [3.0, 9.0]
    assert not list(tmp_path.rglob("*.time"))


def test_unfinished_tool_call_does_not_inflate_later_duration(tmp_path: Path) -> None:
    """A start left by a call that never finished must not be claimed later."""
    before = {
        "hook_event_name": "BeforeTool",
        "tool_name": "run_shell_command",
        "tool_input": {"command": "make"},
        "session_id": "session-one",
        "cwd": "/workspace",
    }
    after = {**before, "hook_event_name": "AfterTool", "tool_response": {}}

    with (
        patch("vauxhall.hooks.common.tempfile.gettempdir", return_value=str(tmp_path)),
        patch("vauxhall.hooks.common.time.time", side_effect=[1000.0, 2000.0, 2003.0]),
    ):
        client = _run(before, before, after)

    assert client.send.call_args.kwargs["duration"] == 3.0
    assert len(list(tmp_path.rglob("*.time"))) == 1
