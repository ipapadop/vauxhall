# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Runtime helpers shared by the built-in agent telemetry hooks."""

import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import redirect_stdout, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vauxhall.core.config import ConfigurationError
from vauxhall.core.logging import get_logger
from vauxhall.hooks.identity import resolve_session_id

if TYPE_CHECKING:
    from vauxhall.hooks.client import TelemetryClient

logger = get_logger(__name__)

Telemetry = tuple[str, dict[str, Any]]
EventHandler = Callable[[dict[str, Any]], Telemetry | None]

_CANCELLATION_MARKERS = frozenset({"cancelled", "canceled", "aborted"})
_SESSION_START_STATUSES = {
    "startup": "Session started",
    "resume": "Session resumed",
    "clear": "Session cleared",
    "fork": "Session forked",
}
_COMPACTION_TRIGGERS = ("manual", "auto")
# Timing directories are per user because the system temporary directory is shared.
_USER_SUFFIX = f"-{os.getuid()}" if hasattr(os, "getuid") else ""


def is_cancelled(response: dict[str, Any]) -> bool:
    """Return whether a tool response contains a cancellation marker."""
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


def question_prompt(tool_input: object) -> str:
    """Extract user-facing question text from a question tool's input."""
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    if isinstance(questions, list):
        prompt = "\n".join(
            question["question"]
            for question in questions
            if isinstance(question, dict) and isinstance(question.get("question"), str)
        )
        if prompt:
            return prompt
    return "User input required"


def tool_details(
    input_data: dict[str, Any], command_fields: Mapping[str, str]
) -> dict[str, Any]:
    """Return the tool name and, for listed tools, the input field shown as cmd."""
    tool_name = input_data.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return {}
    details: dict[str, Any] = {"tool": tool_name}
    tool_input = input_data.get("tool_input")
    field = command_fields.get(tool_name)
    if field is not None and isinstance(tool_input, dict):
        command = tool_input.get(field)
        if isinstance(command, str):
            details["cmd"] = command
    return details


def prompt_submit_telemetry(input_data: dict[str, Any]) -> Telemetry:
    """Translate a submitted user prompt into a thinking state."""
    return "Thinking", {"prompt": input_data.get("prompt", "Processing...")}


def ready_telemetry(_input_data: dict[str, Any]) -> Telemetry:
    """Translate the end of an agent turn into an idle state."""
    return "Idle", {"status": "Ready"}


def permission_request_telemetry(input_data: dict[str, Any]) -> Telemetry:
    """Translate a tool permission request into a waiting state."""
    tool_input = input_data.get("tool_input")
    description = (
        tool_input.get("description") if isinstance(tool_input, dict) else None
    )
    prompt = description if isinstance(description, str) and description else None
    return "Waiting for Input", {
        **tool_details(input_data, {}),
        "prompt": prompt or "Permission required...",
    }


def session_start_telemetry(input_data: dict[str, Any]) -> Telemetry | None:
    """Translate SessionStart without publishing raw sources.

    A restart after compaction can happen in the middle of a turn, so it must not
    mark the session idle.
    """
    source = input_data.get("source")
    if source == "compact":
        return None
    status = (
        _SESSION_START_STATUSES.get(source, "Session started")
        if isinstance(source, str)
        else "Session started"
    )
    return "Idle", {"status": status}


def session_end_telemetry(
    input_data: dict[str, Any], statuses: Mapping[str, str]
) -> Telemetry:
    """Translate SessionEnd using an agent's reason statuses, never raw reasons."""
    reason = input_data.get("reason")
    status = (
        statuses.get(reason, "session ended")
        if isinstance(reason, str)
        else "session ended"
    )
    return "Idle", {"status": status}


def subagent_start_telemetry(input_data: dict[str, Any]) -> Telemetry:
    """Report a starting subagent as the Agent tool running its agent type."""
    details: dict[str, Any] = {"tool": "Agent"}
    agent_type = input_data.get("agent_type")
    if isinstance(agent_type, str) and agent_type:
        details["cmd"] = agent_type
    return "Acting", details


def _is_subagent_event(input_data: dict[str, Any]) -> bool:
    """Return whether an event fired inside a subagent, not the main thread."""
    return isinstance(input_data.get("agent_id"), str)


def pre_compact_telemetry(input_data: dict[str, Any]) -> Telemetry | None:
    """Translate main-thread PreCompact, naming a documented trigger."""
    if _is_subagent_event(input_data):
        return None
    trigger = input_data.get("trigger")
    status = "Compacting context"
    if trigger in _COMPACTION_TRIGGERS:
        status = f"{status} ({trigger})"
    return "Thinking", {"status": status}


def post_compact_telemetry(input_data: dict[str, Any]) -> Telemetry | None:
    """Translate main-thread PostCompact.

    Manual compaction returns to the prompt; automatic compaction resumes work.
    """
    if _is_subagent_event(input_data):
        return None
    state = "Idle" if input_data.get("trigger") == "manual" else "Thinking"
    return state, {"status": "Context compacted"}


def tool_use_identity(input_data: dict[str, Any]) -> tuple[str, str] | None:
    """Return the session and tool-use IDs that identify one tool call, if any."""
    session_id = input_data.get("session_id")
    tool_use_id = input_data.get("tool_use_id")
    if isinstance(session_id, str) and isinstance(tool_use_id, str):
        return session_id, tool_use_id
    return None


def _tool_start_location(agent: str, identity: object) -> tuple[Path, str]:
    """Return an agent's timing directory and the file prefix for one tool call."""
    key = json.dumps(identity, sort_keys=True, default=str)
    digest = hashlib.sha256(key.encode()).hexdigest()
    directory = Path(tempfile.gettempdir()) / f"vauxhall-{agent}{_USER_SUFFIX}"
    return directory, f"{digest}-"


def record_tool_start(agent: str, identity: object) -> None:
    """Record one tool call's start time in its own file.

    Calls that share an identity each get a file; the nanosecond timestamp in the
    name orders them for claim_tool_duration.
    """
    directory, prefix = _tool_start_location(agent, identity)
    with suppress(OSError):
        directory.mkdir(exist_ok=True)
        name = f"{prefix}{time.time_ns():020d}-{os.urandom(8).hex()}"
        pending = directory / f"{name}.tmp"
        pending.write_text(str(time.time()))
        pending.replace(directory / f"{name}.time")


def claim_tool_duration(agent: str, identity: object) -> float | None:
    """Claim the most recent start recorded for a tool call and return its age.

    A start is claimed by renaming its file before reading it, so concurrent
    finishing hooks never share one. Claiming the most recent start keeps a
    start left by a call that never finished from inflating a later call's
    duration. Identical overlapping calls cannot be told apart, so they may
    report each other's durations.
    """
    directory, prefix = _tool_start_location(agent, identity)
    try:
        starts = sorted(directory.glob(f"{prefix}*.time"), reverse=True)
    except OSError:
        return None
    for path in starts:
        claimed = path.with_name(f"{path.stem}.{os.urandom(8).hex()}.claimed")
        try:
            path.rename(claimed)
        except OSError:
            continue  # Another finishing hook claimed this start first.
        try:
            started_at = float(claimed.read_text())
        except (OSError, ValueError):
            continue
        finally:
            claimed.unlink(missing_ok=True)
        return round(time.time() - started_at, 1)
    return None


def create_telemetry_client() -> "TelemetryClient":
    """Create a telemetry client whose connection attempt fits the hook timeout."""
    from vauxhall.hooks.client import TelemetryClient  # noqa: PLC0415

    client = TelemetryClient()
    client.client.connect_timeout = 1.0
    return client


def publish_telemetry(
    input_data: dict[str, Any],
    agent: str,
    handlers: Mapping[str, EventHandler],
    create_client: Callable[[], "TelemetryClient"] | None = None,
) -> None:
    """Translate one hook event with its handler and publish the telemetry.

    Events without a handler, or whose handler returns None, publish nothing.
    """
    hook_type = input_data.get("hook_event_name")
    handler = handlers.get(hook_type) if isinstance(hook_type, str) else None
    telemetry = handler(input_data) if handler is not None else None
    if telemetry is None:
        return

    session_id = resolve_session_id(input_data)
    if session_id is None:
        logger.warning("Skipping telemetry: no stable session identity is available")
        return

    state, details = telemetry
    with (create_client or create_telemetry_client)() as client:
        client.send(
            agent=agent,
            workspace=input_data.get("cwd", str(Path.cwd())),
            session_id=session_id,
            state=state,
            **details,
        )


def run_hook(send_telemetry: Callable[[dict[str, Any]], None]) -> None:
    """Process one hook event from stdin without disrupting the hook protocol."""
    try:
        with redirect_stdout(sys.stderr):
            from vauxhall.core.logging import setup_logging  # noqa: PLC0415
            from vauxhall.hooks.config import hook_settings  # noqa: PLC0415

            setup_logging(level=hook_settings.logging.level)
            input_data = json.load(sys.stdin)
            if isinstance(input_data, dict):
                send_telemetry(input_data)
    except ConfigurationError as error:
        print(error, file=sys.stderr)
    except Exception:
        pass
    print("{}")
