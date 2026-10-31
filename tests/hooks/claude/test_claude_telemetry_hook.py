# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
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

from tests.hooks.recording import record_published
from vauxhall.hooks.claude.telemetry_hook import main

HOOK = "vauxhall.hooks.claude.telemetry_hook"
COMMON = "vauxhall.hooks.common"
BASE = {"session_id": "session-123", "cwd": "/workspace"}


def _run(*events: dict) -> MagicMock:
    """Run the hook for each event and return the recorded events.

    Returns:
        The mock recording each published event.
    """
    with (
        record_published() as published,
        patch("sys.stdout", new=StringIO()),
    ):
        for event in events:
            with patch("sys.stdin", StringIO(json.dumps(event))):
                main()
    return published


def test_claude_publishes_displayed_message_during_turn(tmp_path: Path) -> None:
    """Display batches become one assistant message before the turn stops.

    Args:
        tmp_path: Pytest temporary directory.
    """
    first = {
        **BASE,
        "hook_event_name": "MessageDisplay",
        "message_id": "msg-1",
        "index": 0,
        "delta": "Working ",
        "final": False,
    }
    last = {**first, "index": 1, "delta": "through it.", "final": True}

    with patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)):
        published = _run(first, last)

    published.assert_called_once_with(
        agent="Claude Code",
        workspace="/workspace",
        session_id="native:session-123",
        state="Thinking",
        message="Working through it.",
    )


def test_claude_messages_in_two_workspaces_do_not_share_one_file(
    tmp_path: Path,
) -> None:
    """A session ID is unique only within a workspace, so the key includes it.

    Two workspaces can legitimately share a session ID and a message ID, and
    their interleaved chunks must not be assembled into one message.

    Args:
        tmp_path: Pytest temporary directory.
    """
    display = {
        **BASE,
        "hook_event_name": "MessageDisplay",
        "message_id": "msg-1",
        "final": False,
    }
    here = {**display, "cwd": "/workspace/a", "delta": "from a"}
    there = {**display, "cwd": "/workspace/b", "delta": "from b"}
    here_ends = {**here, "delta": "", "final": True}

    with patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)):
        published = _run(here, there, here_ends)

    published.assert_called_once_with(
        agent="Claude Code",
        workspace="/workspace/a",
        session_id="native:session-123",
        state="Thinking",
        message="from a",
    )


@pytest.mark.parametrize(
    "stdin",
    [
        json.dumps({**BASE, "hook_event_name": "SessionStart", "source": "startup"}),
        json.dumps({**BASE, "hook_event_name": "UnknownEvent"}),
        json.dumps({**BASE, "hook_event_name": "PreToolUse", "tool_input": []}),
        json.dumps({**BASE, "hook_event_name": ["not-a-name"]}),
    ],
)
def test_claude_hook_always_outputs_valid_json(stdin: str) -> None:
    """Every input must exit successfully with one JSON object on stdout.

    Args:
        stdin: The case's stdin contents.
    """
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
                "hook_event_name": "Notification",
                "notification_type": "quota_auto_resume_fired",
                "message": "secret",
            },
            {"state": "Thinking", "status": "Resumed after usage limit"},
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "quota_auto_resume_stale",
            },
            {
                "state": "Waiting for Input",
                "prompt": "Usage limit reset; press Enter to continue",
            },
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "quota_auto_resume_disabled",
                "message": "secret",
            },
            {"state": "Idle", "status": "Stopped waiting for usage limit"},
        ),
        (
            {
                "hook_event_name": "PermissionDenied",
                "tool_name": "Bash",
                "tool_input": {"command": "secret", "description": "secret"},
                "tool_use_id": "toolu_1",
                "reason": "[secret]",
            },
            {"state": "Thinking", "status": "Denied by auto mode: Bash"},
        ),
        (
            {"hook_event_name": "PermissionDenied", "tool_name": ["Edit"]},
            {"state": "Thinking", "status": "Denied by auto mode"},
        ),
        (
            {
                "hook_event_name": "Elicitation",
                "mcp_server_name": "issue-tracker",
                "message": "Choose a project",
                "mode": "url",
                "url": "https://secret.example.com",
                "requested_schema": {"properties": {"secret": {}}},
            },
            {"state": "Waiting for Input", "prompt": "Choose a project"},
        ),
        (
            {
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "message": "   ",
            },
            {"state": "Waiting for Input", "prompt": "Permission required..."},
        ),
        (
            {"hook_event_name": "Elicitation", "message": ["not text"]},
            {"state": "Waiting for Input", "prompt": "Input requested"},
        ),
        (
            {
                "hook_event_name": "ElicitationResult",
                "action": "accept",
                "content": {"username": "secret"},
            },
            {"state": "Acting", "status": "Input accepted"},
        ),
        (
            {"hook_event_name": "ElicitationResult", "action": "decline"},
            {"state": "Acting", "status": "Input declined"},
        ),
        (
            {"hook_event_name": "ElicitationResult", "action": "cancel"},
            {"state": "Acting", "status": "Input cancelled"},
        ),
        (
            {"hook_event_name": "ElicitationResult", "action": "secret"},
            {"state": "Acting", "status": "Input sent"},
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
            {"hook_event_name": "Stop", "last_assistant_message": "Done."},
            {"state": "Idle", "status": "Ready", "message": "Done."},
        ),
        (
            {"hook_event_name": "Stop", "last_assistant_message": ["Done."]},
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
            {"state": "Idle", "status": "session cleared", "end_reason": "clear"},
        ),
        (
            {"hook_event_name": "SessionEnd", "reason": "resume"},
            {"state": "Idle", "status": "session switched", "end_reason": "resume"},
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
    """Each supported event must publish only its normalized dashboard state.

    Args:
        tmp_path: Pytest temporary directory.
        hook_data: The case's hook event.
        expected: The result the case expects.
    """
    with patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)):
        published = _run({**BASE, **hook_data})

    published.assert_called_once_with(
        agent="Claude Code",
        workspace="/workspace",
        session_id="native:session-123",
        **expected,
    )
    assert "secret" not in json.dumps(published.call_args.kwargs)


@pytest.mark.parametrize(
    "hook_data",
    [
        {
            "hook_event_name": "Notification",
            "notification_type": "elicitation_complete",
        },
        {"hook_event_name": "Notification", "notification_type": "auth_success"},
        {"hook_event_name": "Notification", "notification_type": "agent_needs_input"},
        {"hook_event_name": "Notification", "notification_type": "agent_completed"},
        {"hook_event_name": "TeammateIdle", "teammate_name": "researcher"},
        {"hook_event_name": "PostToolBatch", "tool_calls": []},
        {"hook_event_name": "Notification", "notification_type": ["idle_prompt"]},
        {"hook_event_name": "SubagentStop"},
        {"hook_event_name": "SessionStart", "source": "compact"},
        {"hook_event_name": "PreCompact", "trigger": "auto", "agent_id": "agent-1"},
        {"hook_event_name": "PostCompact", "trigger": "auto", "agent_id": "agent-1"},
    ],
)
def test_claude_ignores_events_without_dashboard_state(hook_data: dict) -> None:
    """Events that do not change the main session's state must not publish.

    Args:
        hook_data: The case's hook event.
    """
    published = _run({**BASE, **hook_data})

    published.assert_not_called()


def test_claude_concurrent_tool_durations_use_tool_use_ids(tmp_path: Path) -> None:
    """Concurrent tool calls must retain their own start times.

    Args:
        tmp_path: Pytest temporary directory.
    """

    def event(hook: str, tool_use_id: str) -> dict:
        """Build a Read tool event carrying the given tool-use ID.

        Args:
            hook: Name of the hook event to build.
            tool_use_id: Identifier distinguishing one tool call.

        Returns:
            The event.
        """
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
        published = _run(
            event("PreToolUse", "toolu_a"),
            event("PreToolUse", "toolu_b"),
            event("PostToolUse", "toolu_b"),
            event("PostToolUse", "toolu_a"),
        )

    durations = [
        call.kwargs.get("duration")
        for call in published.call_args_list
        if call.kwargs["state"] == "Thinking"
    ]
    assert durations == [2.0, 7.0]
    assert not list(tmp_path.rglob("*.time"))


def test_claude_failed_tool_reports_duration(tmp_path: Path) -> None:
    """PostToolUseFailure must report the duration recorded for its tool call.

    Args:
        tmp_path: Pytest temporary directory.
    """
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
        published = _run(before, after)

    assert published.call_args.kwargs["duration"] == 2.5


def test_claude_prefers_reported_tool_duration(tmp_path: Path) -> None:
    """Claude Code's duration_ms must win over the hook's own timing file.

    Args:
        tmp_path: Pytest temporary directory.
    """
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
        published = _run(before, after)

    assert published.call_args.kwargs["duration"] == 4.2
    assert not list(tmp_path.rglob("*.time"))


def test_claude_denied_tool_removes_start_without_duration(tmp_path: Path) -> None:
    """PermissionDenied must claim the start record but not report a duration.

    The tool never ran, so the time since PreToolUse is the classifier's.

    Args:
        tmp_path: Pytest temporary directory.
    """
    before = {
        **BASE,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf build"},
        "tool_use_id": "toolu_denied",
    }
    denied = {**before, "hook_event_name": "PermissionDenied", "reason": "[Rule]"}

    with (
        patch(f"{COMMON}.tempfile.gettempdir", return_value=str(tmp_path)),
        patch(f"{COMMON}.time.time", side_effect=[1000.0, 1002.5]),
    ):
        published = _run(before, denied)

    assert published.call_count == 2
    assert published.call_args.kwargs == {
        "agent": "Claude Code",
        "workspace": "/workspace",
        "session_id": "native:session-123",
        "state": "Thinking",
        "status": "Denied by auto mode: Bash",
    }
    assert not list(tmp_path.rglob("*.time"))
