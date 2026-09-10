# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
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

from vauxhall.core.logging import get_logger
from vauxhall.hooks.identity import resolve_session_id

if TYPE_CHECKING:
    from vauxhall.hooks.client import TelemetryClient

logger = get_logger(__name__)


_CANCELLATION_MARKERS = frozenset({"cancelled", "canceled", "aborted"})


def _is_cancelled(response: dict[str, Any]) -> bool:
    """Return whether a Codex tool response contains a cancellation marker."""
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
    """Map a Codex tool response to a truthful telemetry outcome."""
    if not isinstance(response, dict):
        return "Thinking", "result unavailable", None
    if _is_cancelled(response):
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


def _create_telemetry_client() -> "TelemetryClient":
    """Create the telemetry client only inside the hook failure boundary."""
    from vauxhall.hooks.client import TelemetryClient  # noqa: PLC0415

    client = TelemetryClient()
    client.client.connect_timeout = 1.0
    return client


def _setup_logging() -> None:
    """Configure logging inside the hook protocol failure boundary."""
    from vauxhall.core.logging import setup_logging  # noqa: PLC0415
    from vauxhall.hooks.config import hook_settings  # noqa: PLC0415

    setup_logging(level=hook_settings.logging.level)


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
    state, status, error = _classify_tool_response(input_data.get("tool_response"))
    details: dict[str, Any] = {"status": status}
    if tool_name != "unknown":
        details["tool"] = tool_name
    if error is not None:
        details["error"] = error

    time_file = _tool_time_file(input_data)
    if time_file is not None:
        try:
            started_at = float(time_file.read_text().strip())
            details["duration"] = round(time.time() - started_at, 1)
            time_file.unlink()
        except Exception:
            pass
    return state, details


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
    elif hook_type in {"Stop", "SessionEnd"}:
        state = "Idle"
        details = {"status": "Ready"}
    elif hook_type == "Interrupt":
        state = "Idle"
        details = {"status": "interrupted"}
    else:
        return

    session_id = resolve_session_id(input_data)
    if session_id is None:
        logger.warning("Skipping telemetry: no stable session identity is available")
        return

    with _create_telemetry_client() as client:
        client.send(
            agent="Codex",
            workspace=workspace,
            session_id=session_id,
            state=state,
            **details,
        )


def main() -> None:
    """Process one Codex hook event without disrupting its protocol."""
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
