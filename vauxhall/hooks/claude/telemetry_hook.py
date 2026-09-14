# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Claude Code."""

from functools import partial
from typing import Any

from vauxhall.hooks import common

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
    """Add a finished tool call's duration, preferring Claude Code's own timing."""
    identity = common.tool_use_identity(input_data)
    measured = common.claim_tool_duration("claude", identity) if identity else None
    duration_ms = input_data.get("duration_ms")
    if isinstance(duration_ms, int | float) and not isinstance(duration_ms, bool):
        details["duration"] = round(duration_ms / 1000, 1)
    elif measured is not None:
        details["duration"] = measured


def _handle_pre_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Claude Code PreToolUse event."""
    if input_data.get("tool_name") == "AskUserQuestion":
        prompt = common.question_prompt(input_data.get("tool_input"))
        return "Waiting for Input", {"prompt": prompt}

    if (identity := common.tool_use_identity(input_data)) is not None:
        common.record_tool_start("claude", identity)
    return "Acting", common.tool_details(input_data, _COMMAND_FIELDS)


def _handle_post_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Claude Code PostToolUse event, which follows tool success."""
    response = input_data.get("tool_response")
    interrupted = isinstance(response, dict) and (
        response.get("interrupted") is True or common.is_cancelled(response)
    )
    state, status = ("Idle", "cancelled") if interrupted else ("Thinking", "completed")
    details = {**common.tool_details(input_data, {}), "status": status}
    _add_duration(input_data, details)
    return state, details


def _handle_post_tool_failure(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Claude Code PostToolUseFailure event."""
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


def _handle_stop_failure(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate StopFailure, publishing only the documented error type."""
    error = input_data.get("error")
    if not isinstance(error, str) or error not in _STOP_FAILURE_ERRORS:
        error = "unknown"
    return "Error", {"status": "failed", "error": f"API error: {error}"}


_HANDLERS: dict[str, common.EventHandler] = {
    "SessionStart": common.session_start_telemetry,
    "UserPromptSubmit": common.prompt_submit_telemetry,
    "PreToolUse": _handle_pre_tool,
    "PermissionRequest": common.permission_request_telemetry,
    "PostToolUse": _handle_post_tool,
    "PostToolUseFailure": _handle_post_tool_failure,
    "Notification": _handle_notification,
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
