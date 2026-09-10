# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry hook for Gemini CLI.

This script is a unified entry point for all Gemini CLI hook events (BeforeAgent,
AfterAgent, BeforeTool, AfterTool, and Notification). It processes the event JSON
passed via stdin and sends formatted telemetry to the Vauxhall Dashboard.
"""

import hashlib
import json
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from vauxhall.core.logging import get_logger
from vauxhall.hooks.client import TelemetryClient
from vauxhall.hooks.identity import resolve_session_id

logger = get_logger(__name__)


def _tool_time_file(
    workspace: str, session_id: str, input_data: dict[str, Any]
) -> Path:
    """Return a collision-resistant timing file for one Gemini tool call."""
    tool_call_id = input_data.get("tool_call_id")
    identity = session_id
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        identity = f"{identity}\0{tool_call_id.strip()}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return Path(workspace) / ".gemini" / f".vauxhall_tool_start.{digest}.time"


_CANCELLATION_MARKERS = frozenset({"cancelled", "canceled", "aborted"})
_SESSION_END_STATUSES = {
    "exit": "session exited",
    "clear": "session cleared",
    "logout": "logged out",
    "prompt_input_exit": "input closed",
}


def _is_cancelled(response: dict[str, Any]) -> bool:
    """Return whether a Gemini tool response contains a cancellation marker."""
    if response.get("cancelled") is True or response.get("canceled") is True:
        return True
    candidates = [response.get(key) for key in ("code", "status", "name")]
    error = response.get("error")
    if isinstance(error, dict):
        candidates.extend(error.get(key) for key in ("code", "status", "name"))
    return any(
        isinstance(value, str) and value.lower() in _CANCELLATION_MARKERS
        for value in candidates
    )


def _classify_tool_response(response: object) -> tuple[str, str, str | None]:
    """Map a Gemini tool response to a truthful telemetry outcome."""
    if not isinstance(response, dict):
        return "Thinking", "result unavailable", None
    if _is_cancelled(response):
        return "Idle", "cancelled", None
    if response.get("error") is not None:
        return "Error", "failed", "Tool reported an error"
    return "Thinking", "completed", None


def _setup_logging() -> None:
    """Configure logging inside the hook protocol failure boundary."""
    from vauxhall.core.logging import setup_logging  # noqa: PLC0415
    from vauxhall.hooks.config import hook_settings  # noqa: PLC0415

    setup_logging(level=hook_settings.logging.level)


def handle_notification(
    input_data: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Handle Gemini CLI Notification events.

    Args:
        input_data: The hook event data.

    Returns:
        tuple[str, dict[str, Any]] | None: (state, details) or None to ignore.
    """
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
    """Handle Gemini CLI BeforeTool events.

    Args:
        input_data: The hook event data.
        time_file: Path to record the start time.

    Returns:
        tuple[str, dict[str, Any]]: (state, details).
    """
    tool_name = input_data.get("tool_name", input_data.get("tool", "unknown"))
    tool_input = input_data.get("tool_input", input_data.get("arguments", {}))

    # Record start time for duration calculation
    try:
        with time_file.open("w") as f:
            f.write(str(time.time()))
    except Exception:
        pass

    # Handle explicit 'ask_user' and 'ask_question' tool calls
    if tool_name in ["ask_user", "ask_question"]:
        state = "Waiting for Input"
        questions = tool_input.get("questions", [])
        if "question" in tool_input and not questions:
            questions = [{"question": tool_input.get("question")}]
        if questions:
            prompt = "\n".join([q.get("question", "") for q in questions])
            details = {"prompt": prompt}
        else:
            details = {"prompt": "User input required"}
    else:
        state = "Acting"
        # Extract a friendly display string based on the tool being used
        cmd_display = ""
        if tool_name == "run_shell_command":
            cmd_display = tool_input.get("command", "")
        elif tool_name in ["read_file", "write_file", "replace", "view_file"]:
            cmd_display = tool_input.get("file_path", "")

        details = {
            "cmd": cmd_display,
            "args": json.dumps(tool_input),
        }
        if tool_name != "unknown":
            details["tool"] = tool_name

    return state, details


def handle_after_tool(
    input_data: dict[str, Any], time_file: Path
) -> tuple[str, dict[str, Any]]:
    """Handle Gemini CLI AfterTool events.

    Args:
        input_data: The hook event data.
        time_file: Path to read the start time.

    Returns:
        tuple[str, dict[str, Any]]: (state, details).
    """
    tool_name = input_data.get("tool_name", input_data.get("tool", "unknown"))
    state, status, error = _classify_tool_response(input_data.get("tool_response"))
    details: dict[str, Any] = {"status": status}
    if tool_name != "unknown":
        details["tool"] = tool_name
    if error is not None:
        details["error"] = error

    # Calculate duration
    try:
        if time_file.exists():
            with time_file.open() as f:
                start_time = float(f.read().strip())
            duration = round(time.time() - start_time, 1)
            details["duration"] = duration
            time_file.unlink()
    except Exception:
        pass
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


def handle_before_agent(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Handle Gemini CLI BeforeAgent events.

    Args:
        input_data: The hook event data.

    Returns:
        tuple[str, dict[str, Any]]: (state, details).
    """
    state = "Thinking"
    details = {"prompt": input_data.get("prompt", "Processing...")}
    return state, details


def handle_after_agent(_input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Handle Gemini CLI AfterAgent events.

    Args:
        _input_data: The hook event data.

    Returns:
        tuple[str, dict[str, Any]]: (state, details).
    """
    state = "Idle"
    details = {"status": "Ready"}
    return state, details


def handle_after_model(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Handle Gemini CLI AfterModel events.

    Args:
        input_data: The hook event data.

    Returns:
        tuple[str, dict[str, Any]]: (state, details).
    """
    state = "Thinking"
    details = {"status": "Model replied"}
    usage = input_data.get("llm_response", {}).get("usageMetadata", {})
    tokens = usage.get("totalTokenCount")
    if tokens is not None:
        details["tokens"] = tokens
    return state, details


def handle_unknown_hook(hook_type: str) -> tuple[str, dict[str, Any]]:
    """Handle unknown Gemini CLI events.

    Args:
        hook_type: The unrecognized hook event name.

    Returns:
        tuple[str, dict[str, Any]]: (state, details).
    """
    state = "Idle"
    details = {"hook": hook_type}
    return state, details


def _send_telemetry(input_data: dict[str, Any]) -> None:
    """Translate one Gemini hook event and publish its telemetry."""
    hook_type = input_data.get(
        "hook_event_name", input_data.get("hook_type", "BeforeTool")
    )
    workspace = input_data.get("cwd", input_data.get("workspace", str(Path.cwd())))
    agent_name = "Gemini"

    state = "Idle"
    details: dict[str, Any] = {}
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
    if notification_result is not None:
        state, details = notification_result
    elif hook_type == "BeforeAgent":
        state, details = handle_before_agent(input_data)
    elif hook_type == "AfterAgent":
        state, details = handle_after_agent(input_data)
    elif hook_type == "AfterModel":
        state, details = handle_after_model(input_data)
    elif hook_type == "BeforeTool":
        state, details = handle_before_tool(input_data, time_file)
    elif hook_type == "AfterTool":
        state, details = handle_after_tool(input_data, time_file)
    elif hook_type == "SessionEnd":
        state, details = handle_session_end(input_data)
    else:
        state, details = handle_unknown_hook(hook_type)

    with TelemetryClient() as client:
        client.send(
            agent=agent_name,
            workspace=workspace,
            session_id=session_id,
            state=state,
            **details,
        )


def main() -> None:
    """Process a hook event without disrupting the Gemini CLI protocol."""
    try:
        with redirect_stdout(sys.stderr):
            _setup_logging()
            input_data = json.load(sys.stdin)
            if isinstance(input_data, dict):
                _send_telemetry(input_data)
    except Exception:
        pass
    print("{}")


if __name__ == "__main__":
    main()
