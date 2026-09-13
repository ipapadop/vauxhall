# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the Codex telemetry hook."""

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.hooks.codex.telemetry_hook import (
    _classify_tool_response,
    _create_telemetry_client,
    main,
)


def test_codex_hook_outputs_valid_json() -> None:
    """A Codex command hook must exit successfully with valid JSON output."""
    hook_data = {
        "session_id": "test-session",
        "transcript_path": "/workspace/transcript.jsonl",
        "cwd": "/workspace",
        "hook_event_name": "SessionStart",
        "model": "gpt-5",
        "source": "startup",
    }

    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.codex.telemetry_hook"],
        input=json.dumps(hook_data),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert completed.stderr == ""


def test_codex_telemetry_connect_timeout_fits_hook_budget() -> None:
    """MQTT connection setup must finish within the Codex hook timeout."""
    client = _create_telemetry_client()

    assert client.client.connect_timeout == 1.0


def test_codex_hook_keeps_debug_logs_off_stdout() -> None:
    """Debug logging must not contaminate the command hook JSON response."""
    hook_data = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "session_id": "session-123",
        "cwd": "/workspace",
    }
    environment = {
        **os.environ,
        "VAUXHALL_LOGGING_LEVEL": "DEBUG",
        "VAUXHALL_MQTT_HOST": "127.0.0.1",
        "VAUXHALL_MQTT_PORT": "1",
    }

    completed = subprocess.run(
        [sys.executable, "-m", "vauxhall.hooks.codex.telemetry_hook"],
        input=json.dumps(hook_data),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert "Failed to connect telemetry client" in completed.stderr


def test_codex_hook_survives_telemetry_import_failure() -> None:
    """Telemetry import failures must still produce the hook JSON response."""
    command = (
        "import sys; "
        "sys.modules['vauxhall.hooks.client'] = None; "
        "from vauxhall.hooks.codex.telemetry_hook import main; "
        "main()"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        input=json.dumps(
            {
                "hook_event_name": "SessionStart",
                "source": "startup",
                "session_id": "session-123",
                "cwd": "/workspace",
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"


@pytest.mark.parametrize(
    ("environment_value", "file_payload", "expected_source", "expected_value"),
    [
        ("invalid", None, "VAUXHALL_MQTT_PORT", "'invalid'"),
        (None, {"mqtt": []}, "vauxhall_hooks.json", "[]"),
    ],
)
def test_codex_hook_reports_invalid_configuration_without_breaking_protocol(
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
        [sys.executable, "-m", "vauxhall.hooks.codex.telemetry_hook"],
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
        ({"exit_code": 0, "output": "secret"}, "Thinking", "completed", None),
        (
            {"exit_code": 2, "output": "secret"},
            "Error",
            "failed",
            "Bash failed (exit code 2)",
        ),
        (
            {"isError": True, "content": [{"text": "secret"}]},
            "Error",
            "failed",
            "Tool reported an error",
        ),
        (
            {"exit_code": 0, "isError": True},
            "Error",
            "failed",
            "Tool reported an error",
        ),
        ({"cancelled": True, "output": "secret"}, "Idle", "cancelled", None),
        (None, "Thinking", "result unavailable", None),
        ("malformed", "Thinking", "result unavailable", None),
    ],
)
def test_codex_post_tool_outcomes(
    response: object, state: str, status: str, error: str | None
) -> None:
    """PostToolUse responses must map to truthful dashboard outcomes."""
    assert _classify_tool_response(response) == (state, status, error)


def test_codex_post_tool_does_not_publish_response_content() -> None:
    """PostToolUse publishes only normalized outcome fields, never result content."""
    hook_data = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_response": {"exit_code": 2, "output": "secret"},
        "session_id": "session-123",
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        main()

    assert client.send.call_args.kwargs == {
        "agent": "Codex",
        "workspace": "/workspace",
        "state": "Error",
        "tool": "Bash",
        "status": "failed",
        "error": "Bash failed (exit code 2)",
        "session_id": "native:session-123",
    }
    assert "secret" not in json.dumps(client.send.call_args.kwargs)


@pytest.mark.parametrize(
    ("hook_data", "expected"),
    [
        (
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Review the code",
                "session_id": "session-123",
                "cwd": "/workspace",
            },
            {
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-123",
                "state": "Thinking",
                "prompt": "Review the code",
            },
        ),
        (
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status --short"},
                "tool_use_id": "call-123",
                "session_id": "session-123",
                "cwd": "/workspace",
            },
            {
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-123",
                "state": "Acting",
                "tool": "Bash",
                "cmd": "git status --short",
            },
        ),
        (
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "npm install",
                    "description": "Allow dependency installation?",
                },
                "session_id": "session-123",
                "cwd": "/workspace",
            },
            {
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-123",
                "state": "Waiting for Input",
                "tool": "Bash",
                "prompt": "Allow dependency installation?",
            },
        ),
        (
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-123",
                "stop_hook_active": False,
                "session_id": "session-123",
                "cwd": "/workspace",
            },
            {
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-123",
                "state": "Idle",
                "status": "Ready",
            },
        ),
        (
            {
                "hook_event_name": "Interrupt",
                "session_id": "session-123",
                "cwd": "/workspace",
            },
            {
                "agent": "Codex",
                "workspace": "/workspace",
                "state": "Idle",
                "status": "interrupted",
                "session_id": "native:session-123",
            },
        ),
    ],
)
def test_codex_events_publish_dashboard_states(hook_data: dict, expected: dict) -> None:
    """Each supported lifecycle event must publish its dashboard state."""
    output = StringIO()

    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", output),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        main()

    client.send.assert_called_once_with(**expected)
    assert output.getvalue() == "{}\n"


def test_codex_request_user_input_is_waiting() -> None:
    """A request_user_input tool call must surface its question as waiting."""
    hook_data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "request_user_input",
        "tool_input": {
            "questions": [{"question": "Which environment?"}],
        },
        "tool_use_id": "call-question",
        "session_id": "session-123",
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        main()

    client.send.assert_called_once_with(
        agent="Codex",
        workspace="/workspace",
        session_id="native:session-123",
        state="Waiting for Input",
        prompt="Which environment?",
    )


def test_codex_tool_input_does_not_publish_arbitrary_fields() -> None:
    """Tool telemetry must not publish arbitrary potentially sensitive inputs."""
    hook_data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__service__login",
        "tool_input": {"username": "alice", "password": "secret"},
        "tool_use_id": "call-sensitive",
        "session_id": "session-123",
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        main()

    details = client.send.call_args.kwargs
    assert "args" not in details
    assert "secret" not in json.dumps(details)


def test_codex_apply_patch_does_not_publish_patch_contents() -> None:
    """Only Bash commands may populate the command telemetry field."""
    hook_data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": "*** Begin Patch\n+secret\n*** End Patch"},
        "tool_use_id": "call-patch",
        "session_id": "session-123",
        "cwd": "/workspace",
    }

    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        main()

    assert client.send.call_args.kwargs == {
        "agent": "Codex",
        "workspace": "/workspace",
        "session_id": "native:session-123",
        "state": "Acting",
        "tool": "apply_patch",
    }


def test_codex_post_tool_use_reports_duration(tmp_path: Path) -> None:
    """PostToolUse must report the duration recorded for its tool call."""
    before_data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "pwd"},
        "tool_use_id": "call-duration",
        "session_id": "session-duration",
        "cwd": str(tmp_path),
    }
    after_data = {
        **before_data,
        "hook_event_name": "PostToolUse",
        "tool_response": {"output": str(tmp_path), "exit_code": 0},
    }

    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("vauxhall.hooks.codex.telemetry_hook.time.time") as current_time,
        patch(
            "vauxhall.hooks.codex.telemetry_hook.tempfile.gettempdir",
            return_value=str(tmp_path),
        ),
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client

        current_time.return_value = 1000.0
        with patch("sys.stdin", StringIO(json.dumps(before_data))):
            main()

        current_time.return_value = 1002.5
        with patch("sys.stdin", StringIO(json.dumps(after_data))):
            main()

    client.send.assert_called_with(
        agent="Codex",
        workspace=str(tmp_path),
        session_id="native:session-duration",
        state="Thinking",
        tool="Bash",
        status="completed",
        duration=2.5,
    )


def test_codex_telemetry_failure_preserves_hook_protocol() -> None:
    """Telemetry failures must remain invisible to Codex."""
    hook_data = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "session_id": "session-123",
        "cwd": "/workspace",
    }
    output = StringIO()

    with (
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", output),
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client",
            side_effect=RuntimeError,
        ),
    ):
        main()

    assert output.getvalue() == "{}\n"


def test_codex_hook_skips_event_without_stable_session_identity() -> None:
    """Telemetry must be skipped when the hook has no stable identity source."""
    hook_data = {"hook_event_name": "SessionStart", "cwd": "/workspace"}
    with (
        patch(
            "vauxhall.hooks.codex.telemetry_hook._create_telemetry_client"
        ) as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=StringIO()),
        patch.dict("os.environ", {}, clear=True),
    ):
        main()

    client_factory.assert_not_called()
