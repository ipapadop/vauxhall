# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry hook for Gemini CLI.

Reads one hook event (SessionStart, BeforeAgent, AfterAgent, AfterModel,
BeforeTool, AfterTool, Notification, PreCompress, or SessionEnd) as JSON from
stdin and publishes its telemetry.
"""

import json
from functools import partial
from typing import TYPE_CHECKING, Any

from vauxhall.hooks import common
from vauxhall.hooks.identity import resolve_session_id

if TYPE_CHECKING:
    from vauxhall.hooks.client import TelemetryClient
else:
    TelemetryClient = None

# Finish reasons that do not end a streamed model response.
_UNFINISHED_REASONS = ("", "FINISH_REASON_UNSPECIFIED")
_SESSION_END_STATUSES = {
    "exit": "session exited",
    "clear": "session cleared",
    "logout": "logged out",
    "prompt_input_exit": "input closed",
}
# The tool input field shown as cmd for each tool.
_COMMAND_FIELDS = {
    "run_shell_command": "command",
    "read_file": "file_path",
    "write_file": "file_path",
    "replace": "file_path",
}


def _tool_call_identity(input_data: dict[str, Any]) -> list[object]:
    """Identify one Gemini tool call, for which Gemini CLI sends no ID.

    BeforeTool and AfterTool both carry the workspace, session, tool name, and
    tool input.
    """
    return [
        input_data.get("cwd"),
        resolve_session_id(input_data),
        input_data.get("tool_name"),
        input_data.get("tool_input"),
    ]


def _classify_tool_response(response: object) -> tuple[str, str, str | None]:
    """Map a Gemini tool response to a truthful telemetry outcome."""
    if not isinstance(response, dict):
        return "Thinking", "result unavailable", None
    if common.is_cancelled(response):
        return "Idle", "cancelled", None
    if response.get("error") is not None:
        return "Error", "failed", "Tool reported an error"
    return "Thinking", "completed", None


def _create_telemetry_client() -> "TelemetryClient":
    """Create the telemetry client only inside the hook failure boundary."""
    if TelemetryClient is not None:
        return TelemetryClient()

    from vauxhall.hooks.client import (  # noqa: PLC0415
        TelemetryClient as _TelemetryClient,
    )

    return _TelemetryClient()


def _handle_notification(input_data: dict[str, Any]) -> common.Telemetry | None:
    """Map a ToolPermission notification to a waiting state; ignore others."""
    if input_data.get("notification_type", "") != "ToolPermission":
        return None
    # Gemini CLI names the tool only for MCP confirmations, as toolName.
    confirmation = input_data.get("details")
    tool_name = confirmation.get("toolName") if isinstance(confirmation, dict) else None
    details = {"prompt": input_data.get("message", "Permission required...")}
    if isinstance(tool_name, str) and tool_name:
        details["tool"] = tool_name
    return "Waiting for Input", details


def _handle_before_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Record a tool's start time and map BeforeTool to a state and details."""
    common.record_tool_start("gemini", _tool_call_identity(input_data))
    tool_input = input_data.get("tool_input", {})
    if input_data.get("tool_name") == "ask_user":
        return "Waiting for Input", {"prompt": common.question_prompt(tool_input)}
    return "Acting", {
        "cmd": "",
        "args": json.dumps(tool_input),
        **common.tool_details(input_data, _COMMAND_FIELDS),
    }


def _handle_after_tool(input_data: dict[str, Any]) -> common.Telemetry:
    """Map an AfterTool outcome and its duration to a state and details."""
    state, status, error = _classify_tool_response(input_data.get("tool_response"))
    details = {**common.tool_details(input_data, {}), "status": status}
    if error is not None:
        details["error"] = error
    duration = common.claim_tool_duration("gemini", _tool_call_identity(input_data))
    if duration is not None:
        details["duration"] = duration
    return state, details


def _handle_pre_compress(input_data: dict[str, Any]) -> common.Telemetry:
    """Manual compression runs at the prompt; automatic compression is mid-turn."""
    state = "Idle" if input_data.get("trigger") == "manual" else "Thinking"
    return state, {"status": "Compacting context"}


def _is_final_model_response(llm_response: object) -> bool:
    """Return whether a model response chunk carries a finish reason."""
    if not isinstance(llm_response, dict):
        return False
    candidates = llm_response.get("candidates")
    if not isinstance(candidates, list):
        return False
    return any(
        isinstance(candidate, dict)
        and isinstance(candidate.get("finishReason"), str)
        and candidate["finishReason"] not in _UNFINISHED_REASONS
        for candidate in candidates
    )


def _handle_after_model(input_data: dict[str, Any]) -> common.Telemetry | None:
    """Map the final AfterModel chunk to a thinking state with its token count.

    Gemini CLI fires AfterModel for every streamed chunk, so only the chunk that
    finishes the response is published.
    """
    llm_response = input_data.get("llm_response")
    if not _is_final_model_response(llm_response):
        return None
    details: dict[str, Any] = {"status": "Model replied"}
    usage = llm_response.get("usageMetadata")
    if isinstance(usage, dict) and usage.get("totalTokenCount") is not None:
        details["tokens"] = usage["totalTokenCount"]
    return "Thinking", details


_HANDLERS: dict[str, common.EventHandler] = {
    "SessionStart": common.session_start_telemetry,
    "BeforeAgent": common.prompt_submit_telemetry,
    "AfterAgent": common.ready_telemetry,
    "AfterModel": _handle_after_model,
    "BeforeTool": _handle_before_tool,
    "AfterTool": _handle_after_tool,
    "Notification": _handle_notification,
    "PreCompress": _handle_pre_compress,
    "SessionEnd": partial(common.session_end_telemetry, statuses=_SESSION_END_STATUSES),
}


def main() -> None:
    """Process a hook event without disrupting the Gemini CLI protocol."""
    common.run_hook(
        lambda input_data: common.publish_telemetry(
            input_data, "Gemini", _HANDLERS, _create_telemetry_client
        )
    )


if __name__ == "__main__":
    main()
