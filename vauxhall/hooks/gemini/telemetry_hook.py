# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry hook for Gemini CLI.

This script is a unified entry point for all Gemini CLI hook events (BeforeAgent,
AfterAgent, BeforeTool, AfterTool, and Notification). It processes the event JSON
passed via stdin and sends formatted telemetry to the Vauxhall Dashboard.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

from vauxhall.core.logging import setup_logging
from vauxhall.hooks.client import TelemetryClient


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
    state = "Thinking"
    tool_name = input_data.get("tool_name", input_data.get("tool", "unknown"))
    details = {"status": "completed"}
    if tool_name != "unknown":
        details["tool"] = tool_name

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


def main() -> None:
    """Main hook entry point."""
    # Gemini CLI hooks pass event data via stdin
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        # If no valid JSON on stdin, output empty JSON as required by CLI protocol
        print("{}")
        return

    setup_logging()

    hook_type = input_data.get(
        "hook_event_name", input_data.get("hook_type", "BeforeTool")
    )
    workspace = input_data.get("cwd", input_data.get("workspace", str(Path.cwd())))
    time_file = Path(workspace) / ".gemini" / ".vauxhall_tool_start.time"
    agent_name = "Gemini"

    state = "Idle"
    details: dict[str, Any] = {}

    if hook_type == "Notification":
        result = handle_notification(input_data)
        if result:
            state, details = result
        else:
            return
    elif hook_type == "BeforeAgent":
        state = "Thinking"
        details = {"prompt": input_data.get("prompt", "Processing...")}
    elif hook_type == "AfterAgent":
        state = "Idle"
        details = {"status": "Ready"}
    elif hook_type == "AfterModel":
        state = "Thinking"
        details = {"status": "Model replied"}
        usage = input_data.get("llm_response", {}).get("usageMetadata", {})
        tokens = usage.get("totalTokenCount")
        if tokens is not None:
            details["tokens"] = tokens
    elif hook_type == "BeforeTool":
        state, details = handle_before_tool(input_data, time_file)
    elif hook_type == "AfterTool":
        state, details = handle_after_tool(input_data, time_file)
    else:
        state = "Idle"
        details = {"hook": hook_type}

    with TelemetryClient() as client:
        client.send(agent=agent_name, workspace=workspace, state=state, **details)
    print("{}")


if __name__ == "__main__":
    main()
