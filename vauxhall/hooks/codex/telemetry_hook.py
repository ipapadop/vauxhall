# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Codex."""

from functools import partial
from typing import Any

from vauxhall.hooks import common
from vauxhall.hooks.codex.messages import new_messages

_COMMAND_FIELDS = {"Bash": "command"}


def _classify_tool_response(response: object) -> tuple[str, str, str | None]:
    """Map a Codex tool response to a truthful telemetry outcome."""
    if not isinstance(response, dict):
        return "Thinking", "result unavailable", None
    if common.is_cancelled(response):
        return "Idle", "cancelled", None
    exit_code = response.get("exit_code")
    has_exit_code = isinstance(exit_code, int) and not isinstance(exit_code, bool)
    if has_exit_code and exit_code != 0:
        return "Error", "failed", f"Bash failed (exit code {exit_code})"
    if response.get("isError") is True:
        return "Error", "failed", "Tool reported an error"
    if has_exit_code or response.get("isError") is False:
        return "Thinking", "completed", None
    return "Thinking", "result unavailable", None


def _handle_pre_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Codex PreToolUse event."""
    if input_data.get("tool_name") == "request_user_input":
        prompt = common.question_prompt(input_data.get("tool_input"))
        return "Waiting for Input", {"prompt": prompt}

    if (identity := common.tool_use_identity(input_data)) is not None:
        common.record_tool_start("codex", identity)
    return "Acting", common.tool_details(input_data, _COMMAND_FIELDS)


def _handle_post_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Codex PostToolUse event."""
    state, status, error = _classify_tool_response(input_data.get("tool_response"))
    details = {**common.tool_details(input_data, {}), "status": status}
    if error is not None:
        details["error"] = error
    identity = common.tool_use_identity(input_data)
    if identity is not None:
        duration = common.claim_tool_duration("codex", identity)
        if duration is not None:
            details["duration"] = duration
    return state, details


def _handle_stop(input_data: dict[str, Any]) -> common.Telemetry:
    """Publish the final assistant message with the idle state."""
    state, details = common.ready_telemetry(input_data)
    message = common.message_text(input_data.get("last_assistant_message"))
    if message is not None:
        details["message"] = message
    return state, details


_HANDLERS: dict[str, common.EventHandler] = {
    "SessionStart": common.session_start_telemetry,
    "UserPromptSubmit": common.prompt_submit_telemetry,
    "PreToolUse": _handle_pre_tool,
    "PermissionRequest": common.permission_request_telemetry,
    "PostToolUse": _handle_post_tool,
    "SubagentStart": common.subagent_start_telemetry,
    "PreCompact": common.pre_compact_telemetry,
    "PostCompact": common.post_compact_telemetry,
    "Stop": _handle_stop,
    "Interrupt": lambda _: ("Idle", {"status": "interrupted"}),
    # Codex currently reports only the "other" reason.
    "SessionEnd": partial(common.session_end_telemetry, statuses={}),
}


def main() -> None:
    """Process one Codex hook event without disrupting its protocol."""
    common.run_hook(
        lambda input_data: common.publish_telemetry(
            input_data, "Codex", _HANDLERS, messages=new_messages(input_data)
        )
    )


if __name__ == "__main__":
    main()
