# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry hook for Gemini CLI.

This script is a unified entry point for all Gemini CLI hook events (BeforeAgent,
AfterAgent, BeforeTool, AfterTool, and Notification). It processes the event JSON
passed via stdin and sends formatted telemetry to the Vauxhall Dashboard.
"""

import json
import os
import sys
import time

from vauxhall.hooks.client import TelemetryClient
from vauxhall.logging_config import setup_logging


def main():
    # Gemini CLI hooks pass event data via stdin
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        # If no valid JSON on stdin, output empty JSON as required by CLI protocol
        print("{}")
        return

    setup_logging()
    client = TelemetryClient()

    # Gemini CLI event structure:
    # {
    #   "tool_name": "run_shell_command",
    #   "tool_input": {"command": "ls -al"},
    #   "hook_event_name": "BeforeTool" | "AfterTool" | "BeforeAgent" | "AfterAgent" | "AfterModel",
    #   "notification_type": "ToolPermission", (optional)
    #   "message": "...", (optional)
    #   "cwd": "/path/to/project",
    #   "prompt": "User input text" (optional),
    #   "llm_response": { ... } (AfterModel)
    # }

    hook_type = input_data.get(
        "hook_event_name", input_data.get("hook_type", "BeforeTool")
    )
    workspace = input_data.get("cwd", input_data.get("workspace", os.getcwd()))

    # Temporary file for tracking tool execution duration
    time_file = os.path.join(workspace, ".gemini", ".vauxhall_tool_start.time")

    agent_name = "Gemini"
    details = {}

    if hook_type == "Notification":
        notification_type = input_data.get("notification_type", "")
        # Handle safety confirmation prompts
        if notification_type == "ToolPermission":
            state = "Waiting for Input"
            details = {
                "prompt": input_data.get("message", "Permission required..."),
                "tool": input_data.get("details", {}).get("tool_name", "unknown"),
            }
        else:
            # Ignore other notification types for now
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
        # Extract token counts
        usage = input_data.get("llm_response", {}).get("usageMetadata", {})
        tokens = usage.get("totalTokenCount")
        if tokens is not None:
            details["tokens"] = tokens
    elif hook_type == "BeforeTool":
        tool_name = input_data.get("tool_name", input_data.get("tool", "unknown_tool"))
        tool_input = input_data.get("tool_input", input_data.get("arguments", {}))

        # Record start time for duration calculation
        try:
            with open(time_file, "w") as f:
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
                "tool": tool_name,
                "cmd": cmd_display,
                "args": json.dumps(tool_input),
            }
    elif hook_type == "AfterTool":
        state = "Thinking"
        tool_name = input_data.get("tool_name", input_data.get("tool", "unknown_tool"))
        details = {"tool": tool_name, "status": "completed"}

        # Calculate duration
        try:
            if os.path.exists(time_file):
                with open(time_file, "r") as f:
                    start_time = float(f.read().strip())
                duration = round(time.time() - start_time, 1)
                details["duration"] = duration
                os.remove(time_file)
        except Exception:
            pass
    else:
        # Generic fallback for unhandled hook events
        state = "Idle"
        details = {"hook": hook_type}

    # Publish telemetry via MQTT
    client.send(agent=agent_name, workspace=workspace, state=state, **details)

    # Required: output valid JSON to stdout to satisfy CLI hook protocol
    print("{}")


if __name__ == "__main__":
    main()
