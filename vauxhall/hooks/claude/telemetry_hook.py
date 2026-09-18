# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Claude Code."""

from functools import partial
from typing import Any

from vauxhall.hooks import common
from vauxhall.hooks.identity import resolve_session_id

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


def _add_duration(input_data: dict[str, Any], details: dict[str, Any]) -> None:
    """Add a finished tool call's duration, preferring Claude Code's own timing.

    Args:
        input_data: The hook event, read for the agent's reported duration.
        details: Telemetry details the duration is added to, in place.
    """
    identity = common.tool_use_identity(input_data)
    measured = common.claim_tool_duration("claude", identity) if identity else None
    duration_ms = input_data.get("duration_ms")
    if isinstance(duration_ms, int | float) and not isinstance(duration_ms, bool):
        details["duration"] = round(duration_ms / 1000, 1)
    elif measured is not None:
        details["duration"] = measured


def _handle_pre_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Claude Code PreToolUse event.

    Args:
        input_data: The hook event naming the tool about to run.

    Returns:
        The waiting state for a question tool, otherwise the acting state and
        the tool details.
    """
    if input_data.get("tool_name") == "AskUserQuestion":
        prompt = common.question_prompt(input_data.get("tool_input"))
        return "Waiting for Input", {"prompt": prompt}

    if (identity := common.tool_use_identity(input_data)) is not None:
        common.record_tool_start("claude", identity)
    return "Acting", common.tool_details(input_data, _COMMAND_FIELDS)


def _handle_post_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Claude Code PostToolUse event, which follows tool success.

    Args:
        input_data: The hook event carrying the tool response.

    Returns:
        The idle state when the call was interrupted, otherwise the thinking
        state, with the tool details and duration.
    """
    response = input_data.get("tool_response")
    interrupted = isinstance(response, dict) and (
        response.get("interrupted") is True or common.is_cancelled(response)
    )
    state, status = ("Idle", "cancelled") if interrupted else ("Thinking", "completed")
    details = {**common.tool_details(input_data, {}), "status": status}
    _add_duration(input_data, details)
    return state, details


def _handle_post_tool_failure(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Claude Code PostToolUseFailure event.

    Args:
        input_data: The hook event describing the failed call.

    Returns:
        The idle state for an interrupt, otherwise the error state, with the
        tool details and duration.
    """
    details = common.tool_details(input_data, {})
    if input_data.get("is_interrupt") is True:
        state = "Idle"
        details["status"] = "cancelled"
    else:
        state = "Error"
        details["status"] = "failed"
        details["error"] = "Tool reported an error"
    _add_duration(input_data, details)
    return state, details


def _handle_notification(input_data: dict[str, Any]) -> common.Telemetry | None:
    """Map waiting notifications to a waiting state; ignore others.

    Args:
        input_data: The hook event naming the notification type.

    Returns:
        The waiting state and the prompt to show, or ``None`` for a notification
        that does not await the user.
    """
    notification_type = input_data.get("notification_type")
    if not isinstance(notification_type, str):
        return None
    default_prompt = _WAITING_NOTIFICATIONS.get(notification_type)
    if default_prompt is None:
        return None
    message = input_data.get("message")
    prompt = message if isinstance(message, str) and message else default_prompt
    return "Waiting for Input", {"prompt": prompt}


def _handle_stop_failure(input_data: dict[str, Any]) -> common.Telemetry:
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


def _handle_message_display(input_data: dict[str, Any]) -> common.Telemetry | None:
    """Publish an assistant message when its displayed text is complete.

    Args:
        input_data: The hook event carrying one displayed chunk.

    Returns:
        The thinking state and the assembled message, or ``None`` for a chunk
        that does not end one, an event without a message identity, or an
        event fired inside a subagent.
    """
    if common._is_subagent_event(input_data):
        return None
    session_id = resolve_session_id(input_data)
    message_id = input_data.get("message_id")
    if session_id is None or not isinstance(message_id, str) or not message_id:
        return None
    message = common.collect_message_chunk(
        "claude",
        [input_data.get("cwd"), session_id, message_id],
        input_data.get("delta"),
        final=input_data.get("final") is True,
    )
    return ("Thinking", {"message": message}) if message else None


_HANDLERS: dict[str, common.EventHandler] = {
    "SessionStart": common.session_start_telemetry,
    "UserPromptSubmit": common.prompt_submit_telemetry,
    "PreToolUse": _handle_pre_tool,
    "PermissionRequest": common.permission_request_telemetry,
    "PostToolUse": _handle_post_tool,
    "PostToolUseFailure": _handle_post_tool_failure,
    "Notification": _handle_notification,
    "MessageDisplay": _handle_message_display,
    "SubagentStart": common.subagent_start_telemetry,
    "PreCompact": common.pre_compact_telemetry,
    "PostCompact": common.post_compact_telemetry,
    "Stop": common.ready_telemetry,
    "StopFailure": _handle_stop_failure,
    "SessionEnd": partial(common.session_end_telemetry, statuses=_SESSION_END_STATUSES),
}


def main() -> None:
    """Process one Claude Code hook event without disrupting its protocol."""
    common.run_hook(
        partial(common.publish_telemetry, agent="Claude Code", handlers=_HANDLERS)
    )


if __name__ == "__main__":
    main()
