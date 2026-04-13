"""Vauxhall hook for Gemini CLI.

This script processes Gemini CLI tool events and sends telemetry to Vauxhall.
It supports both BeforeTool and AfterTool hooks.
"""

import json
import os
import sys

from vauxhall.hooks.client import TelemetryClient
from vauxhall.logging_config import setup_logging


def main():
    # Gemini CLI hooks pass event data via stdin
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        # If no valid JSON on stdin, we can't do much
        print("{}")
        return

    # Basic setup
    setup_logging()
    client = TelemetryClient()
    
    # Extract info from Gemini event
    # Example event structure (hypothetical, based on common CLI patterns):
    # {
    #   "tool": "run_shell_command",
    #   "arguments": {"command": "ls -al"},
    #   "hook_type": "BeforeTool" | "AfterTool",
    #   "workspace": "/path/to/project"
    # }
    
    # Extract info from Gemini event
    # Gemini CLI structure:
    # {
    #   "tool_name": "run_shell_command",
    #   "tool_input": {"command": "ls -al"},
    #   "hook_event_name": "BeforeTool" | "AfterTool" | "BeforeAgent" | "AfterAgent",
    #   "cwd": "/path/to/project",
    #   "prompt": "User input text"
    # }
    
    hook_type = input_data.get(
        "hook_event_name", input_data.get("hook_type", "BeforeTool")
    )
    workspace = input_data.get("cwd", input_data.get("workspace", os.getcwd()))
    
    agent_name = "Gemini"
    details = {}
    
    if hook_type == "Notification":
        notification_type = input_data.get("notification_type", "")
        if notification_type == "ToolPermission":
            state = "Waiting for Input"
            details = {
                "prompt": input_data.get("message", "Permission required..."),
                "tool": input_data.get("details", {}).get("tool_name", "unknown")
            }
        else:
            # Other notifications can be ignored or handled as thinking/acting
            return
    elif hook_type == "BeforeAgent":
        state = "Thinking"
        details = {
            "prompt": input_data.get("prompt", "Processing...")
        }
    elif hook_type == "AfterAgent":
        state = "Idle"
        details = {
            "status": "Ready"
        }
    elif hook_type == "BeforeTool":
        tool_name = input_data.get("tool_name", input_data.get("tool", "unknown_tool"))
        tool_input = input_data.get("tool_input", input_data.get("arguments", {}))
        
        if tool_name == "ask_user":
            state = "Waiting for Input"
            # Extract questions for prompt
            questions = tool_input.get("questions", [])
            if questions:
                # Concatenate questions into a string
                prompt = "\n".join([q.get("question", "") for q in questions])
                details = {"prompt": prompt}
            else:
                details = {"prompt": "User input required"}
        else:
            state = "Acting"
            
            # Determine a friendly "command" display based on the tool
            cmd_display = ""
            if tool_name == "run_shell_command":
                cmd_display = tool_input.get("command", "")
            elif tool_name in ["read_file", "write_file", "replace", "view_file"]:
                cmd_display = tool_input.get("file_path", "")
            
            details = {
                "tool": tool_name,
                "cmd": cmd_display,
                "args": json.dumps(tool_input)
            }
    elif hook_type == "AfterTool":
        state = "Idle"
        tool_name = input_data.get("tool_name", input_data.get("tool", "unknown_tool"))
        details = {
            "tool": tool_name,
            "status": "completed"
        }
    else:
        # Fallback for unknown hooks
        state = "Idle"
        details = {"hook": hook_type}

    # Send to Vauxhall
    client.send(
        agent=agent_name,
        workspace=workspace,
        state=state,
        **details
    )

    # Required: output valid JSON to stdout
    print("{}")

if __name__ == "__main__":
    main()
