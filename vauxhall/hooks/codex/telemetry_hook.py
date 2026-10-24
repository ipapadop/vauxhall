# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Codex."""

from functools import partial
from typing import Any

from vauxhall.hooks import common
from vauxhall.hooks.codex.messages import new_messages

_COMMAND_FIELDS = {"Bash": "command"}


def _classify_tool_response(response: object) -> tuple[str, str, str | None]:
    """Map a Codex tool response to a truthful telemetry outcome.

    Args:
        response: The tool response to classify.

    Returns:
        The state, the status to show, and an error message when one applies.
    """
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


def _handle_post_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Translate a Codex PostToolUse event.

    Args:
        input_data: The hook event carrying the tool response.

    Returns:
        The state for the response, with the tool details and duration.
    """
    identity = common.tool_use_identity(input_data)
    duration = common.claim_tool_duration("codex", identity) if identity else None
    return common.tool_result_telemetry(
        input_data, _classify_tool_response(input_data.get("tool_response")), duration
    )


HANDLERS: dict[str, common.EventHandler] = {
    "SessionStart": common.session_start_telemetry,
    "UserPromptSubmit": common.prompt_submit_telemetry,
    "PreToolUse": partial(
        common.pre_tool_telemetry,
        agent="codex",
        question_tool="request_user_input",
        command_fields=_COMMAND_FIELDS,
    ),
    "PermissionRequest": common.permission_request_telemetry,
    "PostToolUse": _handle_post_tool,
    "SubagentStart": common.subagent_start_telemetry,
    "PreCompact": common.pre_compact_telemetry,
    "PostCompact": common.post_compact_telemetry,
    "Stop": common.stop_telemetry,
    "Interrupt": lambda _: ("Idle", {"status": "interrupted"}),
    # Codex currently reports only the "other" reason.
    "SessionEnd": partial(common.session_end_telemetry, statuses={}),
}


def main() -> None:
    """Process one Codex hook event without disrupting its protocol."""
    common.run_hook(
        lambda input_data: common.publish_telemetry(
            input_data, "Codex", HANDLERS, messages=new_messages(input_data)
        )
    )


if __name__ == "__main__":
    main()
