# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry hook for Gemini CLI.

Reads one hook event (BeforeAgent, AfterAgent, AfterModel, BeforeTool, AfterTool,
Notification, or SessionEnd) as JSON from stdin and publishes its telemetry.
"""

import hashlib
import json
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
else:
    TelemetryClient = None

logger = get_logger(__name__)


def _tool_time_file(
    workspace: str, session_id: str, input_data: dict[str, Any]
) -> Path:
    """Return a collision-resistant timing file for one Gemini tool call.

    BeforeTool and AfterTool share the call ID when Gemini provides one;
    otherwise they share the tool name and input, which both events carry.
    """
    tool_call_id = input_data.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        call_identity = tool_call_id.strip()
    else:
        call_identity = json.dumps(
            [input_data.get("tool_name"), input_data.get("tool_input")],
            sort_keys=True,
            default=str,
        )
    identity = f"{workspace}\0{session_id}\0{call_identity}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return Path(tempfile.gettempdir()) / f"vauxhall-gemini-{digest}.time"


_SESSION_START_STATUSES = {
    "startup": "Session started",
    "resume": "Session resumed",
    "clear": "Session cleared",
}
_SESSION_END_STATUSES = {
    "exit": "session exited",
    "clear": "session cleared",
    "logout": "logged out",
    "prompt_input_exit": "input closed",
}


def _classify_tool_response(response: object) -> tuple[str, str, str | None]:
    """Map a Gemini tool response to a truthful telemetry outcome."""
    if not isinstance(response, dict):
        return "Thinking", "result unavailable", None
    if is_cancelled(response):
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


def handle_notification(
    input_data: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Map a ToolPermission notification to a waiting state; ignore others."""
    notification_type = input_data.get("notification_type", "")
    if notification_type == "ToolPermission":
        state = "Waiting for Input"
        tool_name = input_data.get("details", {}).get("tool_name", "unknown")
        details = {
            "prompt": input_data.get("message", "Permission required..."),
        }
        if tool_name != "unknown":
            details["tool"] = tool_name
        return state, details
    return None


def handle_before_tool(
    input_data: dict[str, Any], time_file: Path
) -> tuple[str, dict[str, Any]]:
    """Record a tool's start time and map BeforeTool to a state and details."""
    tool_name = input_data.get("tool_name", input_data.get("tool", "unknown"))
    tool_input = input_data.get("tool_input", input_data.get("arguments", {}))

    # Record start time for duration calculation
    with suppress(Exception):
        time_file.write_text(str(time.time()))

    # Handle explicit 'ask_user' and 'ask_question' tool calls
    if tool_name in ("ask_user", "ask_question"):
        questions = tool_input.get("questions", [])
        if "question" in tool_input and not questions:
            questions = [{"question": tool_input.get("question")}]
        if questions:
            prompt = "\n".join(q.get("question", "") for q in questions)
        else:
            prompt = "User input required"
        return "Waiting for Input", {"prompt": prompt}

    # Extract a friendly display string based on the tool being used
    cmd_display = ""
    if tool_name == "run_shell_command":
        cmd_display = tool_input.get("command", "")
    elif tool_name in ("read_file", "write_file", "replace", "view_file"):
        cmd_display = tool_input.get("file_path", "")

    details = {"cmd": cmd_display, "args": json.dumps(tool_input)}
    if tool_name != "unknown":
        details["tool"] = tool_name
    return "Acting", details


def handle_after_tool(
    input_data: dict[str, Any], time_file: Path
) -> tuple[str, dict[str, Any]]:
    """Map an AfterTool outcome and its duration to a state and details."""
    tool_name = input_data.get("tool_name", input_data.get("tool", "unknown"))
    state, status, error = _classify_tool_response(input_data.get("tool_response"))
    details: dict[str, Any] = {"status": status}
    if tool_name != "unknown":
        details["tool"] = tool_name
    if error is not None:
        details["error"] = error

    # Calculate duration
    with suppress(Exception):
        start_time = float(time_file.read_text().strip())
        details["duration"] = round(time.time() - start_time, 1)
        time_file.unlink()
    return state, details


def handle_session_end(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Handle Gemini CLI SessionEnd events without publishing raw reasons."""
    reason = input_data.get("reason")
    status = (
        _SESSION_END_STATUSES.get(reason, "session ended")
        if isinstance(reason, str)
        else "session ended"
    )
    return "Idle", {"status": status}


def handle_session_start(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Handle Gemini CLI SessionStart events without publishing raw sources."""
    source = input_data.get("source")
    status = (
        _SESSION_START_STATUSES.get(source, "Session started")
        if isinstance(source, str)
        else "Session started"
    )
    return "Idle", {"status": status}


def handle_pre_compress(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Manual compression runs at the prompt; automatic compression is mid-turn."""
    state = "Idle" if input_data.get("trigger") == "manual" else "Thinking"
    return state, {"status": "Compacting context"}


def handle_after_model(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map AfterModel to a thinking state with its token count, when present."""
    state = "Thinking"
    details = {"status": "Model replied"}
    usage = input_data.get("llm_response", {}).get("usageMetadata", {})
    tokens = usage.get("totalTokenCount")
    if tokens is not None:
        details["tokens"] = tokens
    return state, details


_EVENT_HANDLERS: dict[str, Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]] = {
    "AfterModel": handle_after_model,
    "SessionStart": handle_session_start,
    "SessionEnd": handle_session_end,
    "PreCompress": handle_pre_compress,
}


def _send_telemetry(input_data: dict[str, Any]) -> None:
    """Translate one Gemini hook event and publish its telemetry."""
    hook_type = input_data.get(
        "hook_event_name", input_data.get("hook_type", "BeforeTool")
    )
    workspace = input_data.get("cwd", input_data.get("workspace", str(Path.cwd())))

    notification_result: tuple[str, dict[str, Any]] | None = None
    if (
        hook_type == "Notification"
        and (notification_result := handle_notification(input_data)) is None
    ):
        return

    session_id = resolve_session_id(input_data)
    if session_id is None:
        logger.warning("Skipping telemetry: no stable session identity is available")
        return

    time_file = _tool_time_file(workspace, session_id, input_data)
    details: dict[str, Any]
    if notification_result is not None:
        state, details = notification_result
    elif hook_type == "BeforeAgent":
        state = "Thinking"
        details = {"prompt": input_data.get("prompt", "Processing...")}
    elif hook_type == "AfterAgent":
        state, details = "Idle", {"status": "Ready"}
    elif hook_type == "BeforeTool":
        state, details = handle_before_tool(input_data, time_file)
    elif hook_type == "AfterTool":
        state, details = handle_after_tool(input_data, time_file)
    elif hook_type in _EVENT_HANDLERS:
        state, details = _EVENT_HANDLERS[hook_type](input_data)
    else:
        state, details = "Idle", {"hook": hook_type}

    with _create_telemetry_client() as client:
        client.send(
            agent="Gemini",
            workspace=workspace,
            session_id=session_id,
            state=state,
            **details,
        )


def main() -> None:
    """Process a hook event without disrupting the Gemini CLI protocol."""
    run_hook(_send_telemetry)


if __name__ == "__main__":
    main()
