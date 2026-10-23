# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the Codex telemetry hook."""

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vauxhall.hooks.codex.telemetry_hook import _classify_tool_response, main


def _run(hook_data: dict) -> MagicMock:
    """Run the Codex hook for one event and return the mocked client.

    Args:
        hook_data: The hook event to feed the hook on stdin.

    Returns:
        The mocked telemetry client.
    """
    with (
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
        patch("sys.stdin", StringIO(json.dumps(hook_data))),
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        main()
    return client


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
        env={
            **os.environ,
            "VAUXHALL_MQTT_HOST": "127.0.0.1",
            "VAUXHALL_MQTT_PORT": "1",
        },
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert completed.stderr == ""


def test_codex_stop_publishes_final_message() -> None:
    """The final assistant reply is sent when Codex completes a turn."""
    client = _run(
        {
            "hook_event_name": "Stop",
            "session_id": "session-123",
            "cwd": "/workspace",
            "last_assistant_message": "Done.",
        }
    )

    client.send.assert_called_once_with(
        agent="Codex",
        workspace="/workspace",
        session_id="native:session-123",
        state="Idle",
        status="Ready",
        message="Done.",
    )


def test_codex_publishes_new_interim_messages_from_transcript(tmp_path: Path) -> None:
    """A tool hook forwards completed commentary from the current Codex turn.

    Args:
        tmp_path: Pytest temporary directory.
    """
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text("", encoding="utf-8")
    base = {
        "session_id": "session-123",
        "cwd": "/workspace",
        "turn_id": "turn-1",
        "transcript_path": str(transcript),
    }
    records = [
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "turn_id": "turn-1",
                "item": {
                    "type": "AgentMessage",
                    "id": "message-1",
                    "phase": "commentary",
                    "content": "First update",
                },
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "turn_id": "turn-1",
                "item": {
                    "type": "AgentMessage",
                    "id": "message-2",
                    "phase": "commentary",
                    "content": "Second update",
                },
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "turn_id": "other",
                "item": {
                    "type": "AgentMessage",
                    "phase": "commentary",
                    "content": "Wrong turn",
                },
            },
        },
    ]

    with patch("vauxhall.hooks.common.tempfile.gettempdir", return_value=str(tmp_path)):
        _run({**base, "hook_event_name": "UserPromptSubmit", "prompt": "Go"})
        with transcript.open("a", encoding="utf-8") as output:
            output.writelines(json.dumps(record) + "\n" for record in records)
        event = {
            **base,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
        }
        client = _run(event)
        repeated = _run(event)

    assert [call.kwargs.get("message") for call in client.send.call_args_list] == [
        "First update",
        "Second update",
        None,
    ]
    repeated.send.assert_called_once()


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
    """PostToolUse responses must map to truthful dashboard outcomes.

    Args:
        response: The case's tool response.
        state: The case's telemetry state.
        status: The case's status.
        error: The case's error.
    """
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
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
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
    """Each supported lifecycle event must publish its dashboard state.

    Args:
        hook_data: The case's hook event.
        expected: The result the case expects.
    """
    output = StringIO()

    with (
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
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
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
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
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
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
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
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
    """PostToolUse must report the duration recorded for its tool call.

    Args:
        tmp_path: Pytest temporary directory.
    """
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
        patch("vauxhall.hooks.common.create_telemetry_client") as client_factory,
        patch("vauxhall.hooks.common.time.time") as current_time,
        patch(
            "vauxhall.hooks.common.tempfile.gettempdir",
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


def test_codex_bash_output_text_reports_result_unavailable() -> None:
    """Codex sends Bash output as text without an exit code."""
    assert _classify_tool_response("Process output\n") == (
        "Thinking",
        "result unavailable",
        None,
    )


@pytest.mark.parametrize(
    ("hook_data", "expected"),
    [
        (
            {"hook_event_name": "SessionStart", "source": source},
            {"state": "Idle", "status": status},
        )
        for source, status in [
            ("startup", "Session started"),
            ("resume", "Session resumed"),
            ("clear", "Session cleared"),
            ("fork", "Session forked"),
            (None, "Session started"),
            (["startup"], "Session started"),
        ]
    ]
    + [
        (
            {
                "hook_event_name": "SubagentStart",
                "agent_id": "agent-1",
                "agent_type": "explorer",
                "turn_id": "turn-1",
            },
            {"state": "Acting", "tool": "Agent", "cmd": "explorer"},
        ),
        (
            {"hook_event_name": "PreCompact", "trigger": "auto", "turn_id": "turn-1"},
            {"state": "Thinking", "status": "Compacting context (auto)"},
        ),
        (
            {"hook_event_name": "PostCompact", "trigger": "manual", "turn_id": "t"},
            {"state": "Idle", "status": "Context compacted"},
        ),
        (
            {"hook_event_name": "PostCompact", "trigger": "auto", "turn_id": "t"},
            {"state": "Thinking", "status": "Context compacted"},
        ),
        (
            {"hook_event_name": "SessionEnd", "reason": "other"},
            {"state": "Idle", "status": "session ended"},
        ),
    ],
)
def test_codex_lifecycle_events_publish_dashboard_states(
    hook_data: dict, expected: dict
) -> None:
    """Codex lifecycle events must publish normalized dashboard states.

    Args:
        hook_data: The case's hook event.
        expected: The result the case expects.
    """
    client = _run({**hook_data, "session_id": "session-123", "cwd": "/w"})

    client.send.assert_called_once_with(
        agent="Codex", workspace="/w", session_id="native:session-123", **expected
    )


@pytest.mark.parametrize(
    "hook_data",
    [
        {"hook_event_name": "SessionStart", "source": "compact"},
        {"hook_event_name": "PreCompact", "trigger": "auto", "agent_id": "agent-1"},
        {"hook_event_name": "PostCompact", "trigger": "auto", "agent_id": "agent-1"},
    ],
)
def test_codex_ignores_events_without_dashboard_state(hook_data: dict) -> None:
    """Events that do not change the main session's state must not publish.

    Args:
        hook_data: The case's hook event.
    """
    client = _run({**hook_data, "session_id": "session-123", "cwd": "/w"})

    client.send.assert_not_called()
