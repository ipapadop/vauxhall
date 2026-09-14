# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the Claude Code telemetry hook."""

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vauxhall.hooks.claude.telemetry_hook import main

HOOK = "vauxhall.hooks.claude.telemetry_hook"
COMMON = "vauxhall.hooks.common"
BASE = {"session_id": "session-123", "cwd": "/workspace"}


def _run(*events: dict) -> MagicMock:
    """Run the hook for each event and return the mocked telemetry client."""
    with (
        patch(f"{COMMON}.create_telemetry_client") as client_factory,
        patch("sys.stdout", new=StringIO()),
    ):
        client = client_factory.return_value
        client.__enter__.return_value = client
        for event in events:
            with patch("sys.stdin", StringIO(json.dumps(event))):
                main()
    return client


@pytest.mark.parametrize(
    "stdin",
    [
        json.dumps({**BASE, "hook_event_name": "SessionStart", "source": "startup"}),
        json.dumps({**BASE, "hook_event_name": "UnknownEvent"}),
        json.dumps({**BASE, "hook_event_name": "PreToolUse", "tool_input": []}),
        json.dumps({**BASE, "hook_event_name": ["not-a-name"]}),
        "not json",
        "[]",
    ],
)
def test_claude_hook_always_outputs_valid_json(stdin: str) -> None:
    """Every input must exit successfully with one JSON object on stdout."""
    completed = subprocess.run(
        [sys.executable, "-m", HOOK],
        input=stdin,
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
            {"hook_event_name": "SessionStart", "source": "fork"},
            {"state": "Idle", "status": "Session forked"},
        ),
        (
            {"hook_event_name": "UserPromptSubmit", "prompt": "Review the code"},
            {"state": "Thinking", "prompt": "Review the code"},
        ),
        (
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status", "description": "Status"},
                "tool_use_id": "toolu_1",
            },
            {"state": "Acting", "tool": "Bash", "cmd": "git status"},
        ),
        (
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "PowerShell",
                "tool_input": {"command": "Get-ChildItem", "description": "List"},
            },
            {"state": "Acting", "tool": "PowerShell", "cmd": "Get-ChildItem"},
        ),
        (
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "/secret.txt", "content": "secret"},
                "tool_use_id": "toolu_2",
            },
            {"state": "Acting", "tool": "Write"},
        ),
        (
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "AskUserQuestion",
                "tool_input": {
                    "questions": [
                        {"question": "Which database?", "options": []},
                        {"question": "Which region?"},
                    ]
                },
            },
            {"state": "Waiting for Input", "prompt": "Which database?\nWhich region?"},
        ),
        (
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf build", "description": "Clean"},
            },
            {"state": "Waiting for Input", "tool": "Bash", "prompt": "Clean"},
        ),
        (
            {"hook_event_name": "PermissionRequest", "tool_name": "Edit"},
            {
                "state": "Waiting for Input",
                "tool": "Edit",
                "prompt": "Permission required...",
            },
        ),
        (
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_response": {"stdout": "secret", "interrupted": False},
            },
            {"state": "Thinking", "tool": "Bash", "status": "completed"},
        ),
        (
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_response": {"stdout": "secret", "interrupted": True},
            },
            {"state": "Idle", "tool": "Bash", "status": "cancelled"},
        ),
        (
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": "secret failure",
                "is_interrupt": False,
            },
            {
                "state": "Error",
                "tool": "Bash",
                "status": "failed",
                "error": "Tool reported an error",
            },
        ),
        (
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": "interrupted",
                "is_interrupt": True,
            },
            {"state": "Idle", "tool": "Bash", "status": "cancelled"},
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "idle_prompt",
                "message": "Claude is waiting for your input",
            },
            {
                "state": "Waiting for Input",
                "prompt": "Claude is waiting for your input",
            },
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "message": "Claude needs your permission",
                "title": "Permission needed",
            },
            {"state": "Waiting for Input", "prompt": "Claude needs your permission"},
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "elicitation_dialog",
            },
            {"state": "Waiting for Input", "prompt": "Input requested"},
        ),
        (
            {
                "hook_event_name": "SubagentStart",
                "agent_id": "agent-abc123",
                "agent_type": "Explore",
            },
            {"state": "Acting", "tool": "Agent", "cmd": "Explore"},
        ),
        (
            {"hook_event_name": "SubagentStart", "agent_id": "agent-abc123"},
            {"state": "Acting", "tool": "Agent"},
        ),
        (
            {
                "hook_event_name": "PreCompact",
                "trigger": "auto",
                "custom_instructions": None,
            },
            {"state": "Thinking", "status": "Compacting context (auto)"},
        ),
        (
            {"hook_event_name": "PreCompact", "trigger": ["auto"]},
            {"state": "Thinking", "status": "Compacting context"},
        ),
        (
            {
                "hook_event_name": "PostCompact",
                "trigger": "manual",
                "compact_summary": "secret",
            },
            {"state": "Idle", "status": "Context compacted"},
        ),
        (
            {
                "hook_event_name": "PostCompact",
                "trigger": "auto",
                "compact_summary": "secret",
            },
            {"state": "Thinking", "status": "Context compacted"},
        ),
        (
            {"hook_event_name": "Stop", "stop_hook_active": False},
            {"state": "Idle", "status": "Ready"},
        ),
        (
            {
                "hook_event_name": "StopFailure",
                "error": "rate_limit",
                "error_details": "secret",
                "last_assistant_message": "secret",
            },
            {"state": "Error", "status": "failed", "error": "API error: rate_limit"},
        ),
        (
            {"hook_event_name": "StopFailure", "error": "secret"},
            {"state": "Error", "status": "failed", "error": "API error: unknown"},
        ),
        (
            {"hook_event_name": "SessionEnd", "reason": "clear"},
            {"state": "Idle", "status": "session cleared"},
        ),
        (
            {"hook_event_name": "SessionEnd", "reason": "resume"},
            {"state": "Idle", "status": "session switched"},
        ),
        (
            {"hook_event_name": "SessionEnd", "reason": "secret"},
            {"state": "Idle", "status": "session ended"},
        ),
    ],
)
def test_claude_events_publish_dashboard_states(
    tmp_path: Path, hook_data: dict, expected: dict
) -> None:
    """Each supported event must publish only its normalized dashboard state."""
    with patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)):
        client = _run({**BASE, **hook_data})

    client.send.assert_called_once_with(
        agent="Claude Code",
        workspace="/workspace",
        session_id="native:session-123",
        **expected,
    )
    assert "secret" not in json.dumps(client.send.call_args.kwargs)


@pytest.mark.parametrize(
    "hook_data",
    [
        {
            "hook_event_name": "Notification",
            "notification_type": "elicitation_complete",
        },
        {"hook_event_name": "Notification", "notification_type": "auth_success"},
        {"hook_event_name": "Notification", "notification_type": ["idle_prompt"]},
        {"hook_event_name": "SubagentStop"},
        {"hook_event_name": "SessionStart", "source": "compact"},
        {"hook_event_name": "PreCompact", "trigger": "auto", "agent_id": "agent-1"},
        {"hook_event_name": "PostCompact", "trigger": "auto", "agent_id": "agent-1"},
    ],
)
def test_claude_ignores_events_without_dashboard_state(hook_data: dict) -> None:
    """Events that do not change the main session's state must not publish."""
    client = _run({**BASE, **hook_data})

    client.send.assert_not_called()


def test_claude_concurrent_tool_durations_use_tool_use_ids(tmp_path: Path) -> None:
    """Concurrent tool calls must retain their own start times."""

    def event(hook: str, tool_use_id: str) -> dict:
        return {
            **BASE,
            "hook_event_name": hook,
            "tool_name": "Read",
            "tool_input": {"file_path": "/workspace/a.txt"},
            "tool_use_id": tool_use_id,
            "tool_response": {},
        }

    with (
        patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)),
        patch(f"{COMMON}.time.time", side_effect=[1000.0, 1001.0, 1003.0, 1007.0]),
    ):
        client = _run(
            event("PreToolUse", "toolu_a"),
            event("PreToolUse", "toolu_b"),
            event("PostToolUse", "toolu_b"),
            event("PostToolUse", "toolu_a"),
        )

    durations = [
        call.kwargs.get("duration")
        for call in client.send.call_args_list
        if call.kwargs["state"] == "Thinking"
    ]
    assert durations == [2.0, 7.0]
    assert not list(tmp_path.rglob("*.time"))


def test_claude_failed_tool_reports_duration(tmp_path: Path) -> None:
    """PostToolUseFailure must report the duration recorded for its tool call."""
    before = {
        **BASE,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "false"},
        "tool_use_id": "toolu_fail",
    }
    after = {**before, "hook_event_name": "PostToolUseFailure", "error": "exit 1"}

    with (
        patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)),
        patch(f"{COMMON}.time.time", side_effect=[1000.0, 1002.5]),
    ):
        client = _run(before, after)

    assert client.send.call_args.kwargs["duration"] == 2.5


def test_claude_prefers_reported_tool_duration(tmp_path: Path) -> None:
    """Claude Code's duration_ms must win over the hook's own timing file."""
    before = {
        **BASE,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "tool_use_id": "toolu_reported",
    }
    after = {
        **before,
        "hook_event_name": "PostToolUse",
        "tool_response": {},
        "duration_ms": 4187,
    }

    with (
        patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)),
        patch(f"{COMMON}.time.time", side_effect=[1000.0, 2000.0]),
    ):
        client = _run(before, after)

    assert client.send.call_args.kwargs["duration"] == 4.2
    assert not list(tmp_path.rglob("*.time"))


def test_claude_hook_skips_event_without_stable_session_identity() -> None:
    """Telemetry must be skipped when the hook has no stable identity source."""
    with (
        patch(f"{COMMON}.create_telemetry_client") as client_factory,
        patch("sys.stdin", StringIO(json.dumps({"hook_event_name": "Stop"}))),
        patch("sys.stdout", new=StringIO()),
        patch.dict("os.environ", {}, clear=True),
    ):
        main()

    client_factory.assert_not_called()
