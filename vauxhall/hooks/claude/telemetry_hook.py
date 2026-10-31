# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Claude Code."""

from functools import partial
from typing import Any

from vauxhall.hooks import events, runner, scratch
from vauxhall.hooks.identity import resolve_session_id
from vauxhall.hooks.text import message_text

_COMMAND_FIELDS = {"Bash": "command", "PowerShell": "command"}
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
    "quota_auto_resume_stale": "Usage limit reset; press Enter to continue",
}
# Notification types that change the state without awaiting the user. Their
# messages are not published. agent_needs_input and agent_completed describe
# other sessions, so they are ignored like SubagentStop.
_STATUS_NOTIFICATIONS = {
    "quota_auto_resume_fired": ("Thinking", "Resumed after usage limit"),
    "quota_auto_resume_disabled": ("Idle", "Stopped waiting for usage limit"),
}
_ELICITATION_STATUSES = {
    "accept": "Input accepted",
    "decline": "Input declined",
    "cancel": "Input cancelled",
}
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


def _tool_duration(input_data: dict[str, Any]) -> float | None:
    """Return a finished tool call's duration, preferring Claude Code's own timing.

    Args:
        input_data: The hook event, read for the agent's reported duration.

    Returns:
        The duration in seconds, or ``None`` when unknown.
    """
    # Claimed even when Claude Code reports a duration, to remove the start record.
    measured = scratch.claim_tool_use_duration("claude", input_data)
    duration_ms = input_data.get("duration_ms")
    if isinstance(duration_ms, int | float) and not isinstance(duration_ms, bool):
        return round(duration_ms / 1000, 1)
    return measured


def _handle_post_tool(input_data: dict[str, Any]) -> events.Telemetry:
    """Translate a Claude Code PostToolUse event, which follows tool success.

    Args:
        input_data: The hook event carrying the tool response.

    Returns:
        The idle state when the call was interrupted, otherwise the thinking
        state, with the tool details and duration.
    """
    response = input_data.get("tool_response")
    interrupted = isinstance(response, dict) and (
        response.get("interrupted") is True or events.is_cancelled(response)
    )
    outcome = (
        ("Idle", "cancelled", None) if interrupted else ("Thinking", "completed", None)
    )
    return events.tool_result_telemetry(input_data, outcome, _tool_duration(input_data))


def _handle_post_tool_failure(input_data: dict[str, Any]) -> events.Telemetry:
    """Translate a Claude Code PostToolUseFailure event.

    Args:
        input_data: The hook event describing the failed call.

    Returns:
        The idle state for an interrupt, otherwise the error state, with the
        tool details and duration.
    """
    if input_data.get("is_interrupt") is True:
        outcome = ("Idle", "cancelled", None)
    else:
        outcome = ("Error", "failed", "Tool reported an error")
    return events.tool_result_telemetry(input_data, outcome, _tool_duration(input_data))


def _handle_permission_denied(input_data: dict[str, Any]) -> events.Telemetry:
    """Translate PermissionDenied, sent when auto mode refuses a tool call.

    The model receives the denial and continues, so the state is thinking. The
    tool is named in the status alone: the activity log shows an ``error`` as
    an error and a ``tool`` as running. The denial reason is not published.

    Args:
        input_data: The hook event naming the denied tool.

    Returns:
        The thinking state and a status naming the denied tool.
    """
    # Remove the start record; the tool never ran, so report no duration.
    scratch.claim_tool_use_duration("claude", input_data)
    tool = events.tool_details(input_data, {}).get("tool")
    status = f"Denied by auto mode: {tool}" if tool else "Denied by auto mode"
    return "Thinking", {"status": status}


def _waiting_telemetry(
    input_data: dict[str, Any], default_prompt: str
) -> events.Telemetry:
    """Build a waiting state that shows the event's message when it has one.

    Args:
        input_data: The hook event, read for its message.
        default_prompt: The prompt shown when the event has no message.

    Returns:
        The waiting state and the prompt to show.
    """
    prompt = message_text(input_data.get("message")) or default_prompt
    return "Waiting for Input", {"prompt": prompt}


def _handle_notification(input_data: dict[str, Any]) -> events.Telemetry | None:
    """Map waiting and usage-limit notifications to a state; ignore others.

    Args:
        input_data: The hook event naming the notification type.

    Returns:
        The waiting state and the prompt to show, a usage-limit state and
        status, or ``None`` for any other notification.
    """
    notification_type = input_data.get("notification_type")
    if not isinstance(notification_type, str):
        return None
    status = _STATUS_NOTIFICATIONS.get(notification_type)
    if status is not None:
        state, text = status
        return state, {"status": text}
    default_prompt = _WAITING_NOTIFICATIONS.get(notification_type)
    if default_prompt is None:
        return None
    return _waiting_telemetry(input_data, default_prompt)


def _handle_elicitation_result(input_data: dict[str, Any]) -> events.Telemetry:
    """Translate the user's answer to an MCP elicitation; the tool call resumes.

    Args:
        input_data: The hook event naming the user's action.

    Returns:
        The acting state and the action taken. The submitted content is not
        published.
    """
    action = input_data.get("action")
    status = _ELICITATION_STATUSES.get(action) if isinstance(action, str) else None
    return "Acting", {"status": status or "Input sent"}


def _handle_stop_failure(input_data: dict[str, Any]) -> events.Telemetry:
    """Translate StopFailure, publishing only the documented error type.

    Args:
        input_data: The hook event naming the error.

    Returns:
        The error state and a status naming a documented error, or "unknown".
    """
    error = input_data.get("error")
    if not isinstance(error, str) or error not in _STOP_FAILURE_ERRORS:
        error = "unknown"
    return "Error", {"status": "failed", "error": f"API error: {error}"}


def _handle_message_display(input_data: dict[str, Any]) -> events.Telemetry | None:
    """Publish an assistant message when its displayed text is complete.

    Args:
        input_data: The hook event carrying one displayed chunk.

    Returns:
        The thinking state and the assembled message, or ``None`` for a chunk
        that does not end one, an event without a message identity, or an
        event fired inside a subagent.
    """
    if events.is_subagent_event(input_data):
        return None
    session_id = resolve_session_id(input_data)
    message_id = input_data.get("message_id")
    if session_id is None or not isinstance(message_id, str) or not message_id:
        return None
    message = scratch.collect_message_chunk(
        "claude",
        [input_data.get("cwd"), session_id, message_id],
        input_data.get("delta"),
        final=input_data.get("final") is True,
    )
    return ("Thinking", {"message": message}) if message else None


HANDLERS: dict[str, events.EventHandler] = {
    "SessionStart": events.session_start_telemetry,
    "UserPromptSubmit": events.prompt_submit_telemetry,
    "PreToolUse": partial(
        events.pre_tool_telemetry,
        agent="claude",
        question_tool="AskUserQuestion",
        command_fields=_COMMAND_FIELDS,
    ),
    "PermissionRequest": events.permission_request_telemetry,
    "PermissionDenied": _handle_permission_denied,
    "PostToolUse": _handle_post_tool,
    "PostToolUseFailure": _handle_post_tool_failure,
    "Notification": _handle_notification,
    # Fires when the server asks, before the elicitation_dialog notification.
    "Elicitation": partial(_waiting_telemetry, default_prompt="Input requested"),
    "ElicitationResult": _handle_elicitation_result,
    "MessageDisplay": _handle_message_display,
    "SubagentStart": events.subagent_start_telemetry,
    "PreCompact": events.pre_compact_telemetry,
    "PostCompact": events.post_compact_telemetry,
    "Stop": events.stop_telemetry,
    "StopFailure": _handle_stop_failure,
    "SessionEnd": partial(events.session_end_telemetry, statuses=_SESSION_END_STATUSES),
}


def main() -> None:
    """Process one Claude Code hook event without disrupting its protocol."""
    runner.run_hook(
        partial(runner.publish_telemetry, agent="Claude Code", handlers=HANDLERS)
    )


if __name__ == "__main__":
    main()
