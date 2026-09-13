# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Claude Code."""

import hashlib
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vauxhall.core.logging import get_logger
from vauxhall.hooks.common import is_cancelled, run_hook
from vauxhall.hooks.identity import resolve_session_id

if TYPE_CHECKING:
    from vauxhall.hooks.client import TelemetryClient

logger = get_logger(__name__)

_Telemetry = tuple[str, dict[str, Any]]

_SESSION_START_STATUSES = {
    "startup": "Session started",
    "resume": "Session resumed",
    "clear": "Session cleared",
    "fork": "Session forked",
}
_SESSION_END_STATUSES = {
    "clear": "session cleared",
    "resume": "session switched",
    "logout": "logged out",
    "prompt_input_exit": "input closed",
}
# Notification types that mean Claude Code is waiting for the user, with the
# prompt shown when the notification carries no message. PermissionRequest
# reports tool permissions immediately; permission_prompt follows after a delay
# and is the only signal for sandboxed network requests.
_WAITING_NOTIFICATIONS = {
    "permission_prompt": "Permission required...",
    "idle_prompt": "Waiting for your input",
    "elicitation_dialog": "Input requested",
    "elicitation_url_dialog": "Input requested",
}
_COMPACTION_TRIGGERS = ("manual", "auto")
_STOP_FAILURE_ERRORS = frozenset(
    {
        "rate_limit",
        "overloaded",
        "authentication_failed",
        "oauth_org_not_allowed",
        "account_on_hold",
        "billing_error",
        "invalid_request",
        "model_not_found",
        "server_error",
        "max_output_tokens",
        "cloud_credential_error",
        "unknown",
    }
)


def _create_telemetry_client() -> "TelemetryClient":
    """Create the telemetry client only inside the hook failure boundary."""
    from vauxhall.hooks.client import TelemetryClient  # noqa: PLC0415

    client = TelemetryClient()
    client.client.connect_timeout = 1.0
    return client


def _tool_time_file(input_data: dict[str, Any]) -> Path | None:
    """Return a collision-resistant timing file for one Claude Code tool call."""
    session_id = input_data.get("session_id")
    tool_use_id = input_data.get("tool_use_id")
    if not isinstance(session_id, str) or not isinstance(tool_use_id, str):
        return None
    digest = hashlib.sha256(f"{session_id}\0{tool_use_id}".encode()).hexdigest()
    return Path(tempfile.gettempdir()) / f"vauxhall-claude-{digest}.time"


def _tool_details(input_data: dict[str, Any]) -> dict[str, Any]:
    """Return the tool name detail when the event names a tool."""
    tool_name = input_data.get("tool_name")
    return {"tool": tool_name} if isinstance(tool_name, str) and tool_name else {}


def _add_duration(input_data: dict[str, Any], details: dict[str, Any]) -> None:
    """Add a finished tool call's duration, preferring Claude Code's own timing."""
    duration_ms = input_data.get("duration_ms")
    if isinstance(duration_ms, int | float) and not isinstance(duration_ms, bool):
        details["duration"] = round(duration_ms / 1000, 1)
    time_file = _tool_time_file(input_data)
    if time_file is None:
        return
    with suppress(Exception):
        if "duration" not in details:
            started_at = float(time_file.read_text().strip())
            details["duration"] = round(time.time() - started_at, 1)
        time_file.unlink()


def _question_prompt(tool_input: object) -> str:
    """Extract user-facing question text from an AskUserQuestion input."""
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    if isinstance(questions, list):
        prompt = "\n".join(
            question["question"]
            for question in questions
            if isinstance(question, dict) and isinstance(question.get("question"), str)
        )
        if prompt:
            return prompt
    return "User input required"


def _handle_pre_tool(input_data: dict[str, Any]) -> _Telemetry:
    """Translate a Claude Code PreToolUse event."""
    tool_input = input_data.get("tool_input")
    if input_data.get("tool_name") == "AskUserQuestion":
        return "Waiting for Input", {"prompt": _question_prompt(tool_input)}

    time_file = _tool_time_file(input_data)
    if time_file is not None:
        with suppress(Exception):
            time_file.write_text(str(time.time()))

    details = _tool_details(input_data)
    if details.get("tool") == "Bash" and isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            details["cmd"] = command
    return "Acting", details


def _handle_post_tool(input_data: dict[str, Any]) -> _Telemetry:
    """Translate a Claude Code PostToolUse event, which follows tool success."""
    response = input_data.get("tool_response")
    interrupted = isinstance(response, dict) and (
        response.get("interrupted") is True or is_cancelled(response)
    )
    state, status = ("Idle", "cancelled") if interrupted else ("Thinking", "completed")
    details = {**_tool_details(input_data), "status": status}
    _add_duration(input_data, details)
    return state, details


def _handle_post_tool_failure(input_data: dict[str, Any]) -> _Telemetry:
    """Translate a Claude Code PostToolUseFailure event."""
    details = _tool_details(input_data)
    if input_data.get("is_interrupt") is True:
        state = "Idle"
        details["status"] = "cancelled"
    else:
        state = "Error"
        details["status"] = "failed"
        details["error"] = "Tool reported an error"
    _add_duration(input_data, details)
    return state, details


def _handle_permission(input_data: dict[str, Any]) -> _Telemetry:
    """Translate a Claude Code PermissionRequest event."""
    tool_input = input_data.get("tool_input")
    description = (
        tool_input.get("description") if isinstance(tool_input, dict) else None
    )
    prompt = description if isinstance(description, str) and description else None
    return "Waiting for Input", {
        **_tool_details(input_data),
        "prompt": prompt or "Permission required...",
    }


def _handle_notification(input_data: dict[str, Any]) -> _Telemetry | None:
    """Map waiting notifications to a waiting state; ignore others."""
    notification_type = input_data.get("notification_type")
    if not isinstance(notification_type, str):
        return None
    default_prompt = _WAITING_NOTIFICATIONS.get(notification_type)
    if default_prompt is None:
        return None
    message = input_data.get("message")
    prompt = message if isinstance(message, str) and message else default_prompt
    return "Waiting for Input", {"prompt": prompt}


def _handle_session_start(input_data: dict[str, Any]) -> _Telemetry | None:
    """Translate SessionStart; PostCompact reports restarts after compaction."""
    source = input_data.get("source")
    if source == "compact":
        return None
    status = (
        _SESSION_START_STATUSES.get(source, "Session started")
        if isinstance(source, str)
        else "Session started"
    )
    return "Idle", {"status": status}


def _handle_session_end(input_data: dict[str, Any]) -> _Telemetry:
    """Translate SessionEnd without publishing raw reasons."""
    reason = input_data.get("reason")
    status = (
        _SESSION_END_STATUSES.get(reason, "session ended")
        if isinstance(reason, str)
        else "session ended"
    )
    return "Idle", {"status": status}


def _handle_subagent_start(input_data: dict[str, Any]) -> _Telemetry:
    """Translate SubagentStart into the Agent tool running the subagent type."""
    details: dict[str, Any] = {"tool": "Agent"}
    agent_type = input_data.get("agent_type")
    if isinstance(agent_type, str) and agent_type:
        details["cmd"] = agent_type
    return "Acting", details


def _handle_pre_compact(input_data: dict[str, Any]) -> _Telemetry:
    """Translate PreCompact, naming a documented trigger when present."""
    trigger = input_data.get("trigger")
    status = "Compacting context"
    if trigger in _COMPACTION_TRIGGERS:
        status = f"{status} ({trigger})"
    return "Thinking", {"status": status}


def _handle_post_compact(input_data: dict[str, Any]) -> _Telemetry:
    """Manual compaction returns to the prompt; automatic compaction resumes work."""
    state = "Idle" if input_data.get("trigger") == "manual" else "Thinking"
    return state, {"status": "Context compacted"}


def _handle_stop_failure(input_data: dict[str, Any]) -> _Telemetry:
    """Translate StopFailure, publishing only the documented error type."""
    error = input_data.get("error")
    if not isinstance(error, str) or error not in _STOP_FAILURE_ERRORS:
        error = "unknown"
    return "Error", {"status": "failed", "error": f"API error: {error}"}


_HANDLERS: dict[str, Callable[[dict[str, Any]], _Telemetry | None]] = {
    "SessionStart": _handle_session_start,
    "UserPromptSubmit": lambda data: (
        "Thinking",
        {"prompt": data.get("prompt", "Processing...")},
    ),
    "PreToolUse": _handle_pre_tool,
    "PermissionRequest": _handle_permission,
    "PostToolUse": _handle_post_tool,
    "PostToolUseFailure": _handle_post_tool_failure,
    "Notification": _handle_notification,
    "SubagentStart": _handle_subagent_start,
    "PreCompact": _handle_pre_compact,
    "PostCompact": _handle_post_compact,
    "Stop": lambda _: ("Idle", {"status": "Ready"}),
    "StopFailure": _handle_stop_failure,
    "SessionEnd": _handle_session_end,
}


def _send_telemetry(input_data: dict[str, Any]) -> None:
    """Translate one Claude Code hook event and publish its telemetry."""
    hook_type = input_data.get("hook_event_name")
    handler = _HANDLERS.get(hook_type) if isinstance(hook_type, str) else None
    telemetry = handler(input_data) if handler is not None else None
    if telemetry is None:
        return
    state, details = telemetry

    session_id = resolve_session_id(input_data)
    if session_id is None:
        logger.warning("Skipping telemetry: no stable session identity is available")
        return

    with _create_telemetry_client() as client:
        client.send(
            agent="Claude Code",
            workspace=input_data.get("cwd", str(Path.cwd())),
            session_id=session_id,
            state=state,
            **details,
        )


def main() -> None:
    """Process one Claude Code hook event without disrupting its protocol."""
    run_hook(_send_telemetry)


if __name__ == "__main__":
    main()
