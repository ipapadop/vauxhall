# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall telemetry command hook for Codex."""

import hashlib
import json
import sys
import tempfile
import time
from contextlib import redirect_stdout, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vauxhall.hooks.client import TelemetryClient


def _create_telemetry_client() -> "TelemetryClient":
    """Create the telemetry client only inside the hook failure boundary."""
    from vauxhall.hooks.client import TelemetryClient  # noqa: PLC0415

    client = TelemetryClient()
    client.client.connect_timeout = 1.0
    return client


def _tool_time_file(input_data: dict[str, Any]) -> Path | None:
    """Return a collision-resistant timing file for one Codex tool call."""
    session_id = input_data.get("session_id")
    tool_use_id = input_data.get("tool_use_id")
    if not isinstance(session_id, str) or not isinstance(tool_use_id, str):
        return None
    digest = hashlib.sha256(f"{session_id}\0{tool_use_id}".encode()).hexdigest()
    return Path(tempfile.gettempdir()) / f"vauxhall-codex-{digest}.time"


def _question_prompt(tool_input: object) -> str:
    """Extract user-facing question text from a Codex tool input."""
    if not isinstance(tool_input, dict):
        return "User input required"
    questions = tool_input.get("questions", [])
    if isinstance(questions, list):
        prompt = "\n".join(
            question.get("question", "")
            for question in questions
            if isinstance(question, dict)
        )
        if prompt:
            return prompt
    question = tool_input.get("question")
    return question if isinstance(question, str) else "User input required"


def _handle_pre_tool(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate a Codex PreToolUse event."""
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    if tool_name == "request_user_input":
        return "Waiting for Input", {"prompt": _question_prompt(tool_input)}

    time_file = _tool_time_file(input_data)
    if time_file is not None:
        with suppress(Exception):
            time_file.write_text(str(time.time()))

    details: dict[str, Any] = {}
    if tool_name == "Bash" and isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            details["cmd"] = command
    if tool_name != "unknown":
        details["tool"] = tool_name
    return "Acting", details


def _handle_post_tool(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate a Codex PostToolUse event."""
    tool_name = input_data.get("tool_name", "unknown")
    details: dict[str, Any] = {"status": "completed"}
    if tool_name != "unknown":
        details["tool"] = tool_name

    time_file = _tool_time_file(input_data)
    if time_file is not None:
        try:
            started_at = float(time_file.read_text().strip())
            details["duration"] = round(time.time() - started_at, 1)
            time_file.unlink()
        except Exception:
            pass
    return "Thinking", details


def _handle_permission(input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate a Codex PermissionRequest event."""
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    description = (
        tool_input.get("description") if isinstance(tool_input, dict) else None
    )
    details: dict[str, Any] = {
        "prompt": description or "Permission required...",
    }
    if tool_name != "unknown":
        details["tool"] = tool_name
    return "Waiting for Input", details


def _send_telemetry(input_data: dict[str, Any]) -> None:
    """Translate one Codex hook event and publish its telemetry."""
    hook_type = input_data.get("hook_event_name", "")
    workspace = input_data.get("cwd", str(Path.cwd()))

    if hook_type == "UserPromptSubmit":
        state = "Thinking"
        details = {"prompt": input_data.get("prompt", "Processing...")}
    elif hook_type == "PreToolUse":
        state, details = _handle_pre_tool(input_data)
    elif hook_type == "PostToolUse":
        state, details = _handle_post_tool(input_data)
    elif hook_type == "PermissionRequest":
        state, details = _handle_permission(input_data)
    elif hook_type == "SessionStart":
        state = "Thinking"
        details = {"status": "Session started"}
    elif hook_type in {"Stop", "Interrupt", "SessionEnd"}:
        state = "Idle"
        details = {"status": "Ready"}
    else:
        return

    with _create_telemetry_client() as client:
        client.send(agent="Codex", workspace=workspace, state=state, **details)


def main() -> None:
    """Process one Codex hook event without disrupting its protocol."""
    try:
        with redirect_stdout(sys.stderr):
            input_data = json.load(sys.stdin)
            if isinstance(input_data, dict):
                _send_telemetry(input_data)
    except Exception:
        pass
    print("{}")


if __name__ == "__main__":
    main()
