# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Hook event handlers shared by the built-in agent telemetry hooks.

A handler translates one hook event into a state and its details, or into
``None`` to publish nothing.
"""

from collections.abc import Callable, Mapping
from typing import Any

from vauxhall.hooks.scratch import record_tool_start, tool_use_identity
from vauxhall.hooks.text import message_text

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


def is_cancelled(response: dict[str, Any]) -> bool:
    """Return whether a tool response contains a cancellation marker.

    Args:
        response: The tool response to inspect.

    Returns:
        Whether the response reports the call as cancelled or aborted.
    """
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
    """Extract user-facing question text from a question tool's input.

    Args:
        tool_input: The question tool's input.

    Returns:
        The questions joined by newlines, or a generic prompt when the input
        carries none.
    """
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
    """Return the tool name and, for listed tools, the input field shown as cmd.

    Args:
        input_data: The hook event naming the tool and its input.
        command_fields: Input field to show as ``cmd``, keyed by tool name.

    Returns:
        The details to publish, empty when the event names no tool.
    """
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
    """Translate a submitted user prompt into a thinking state.

    Args:
        input_data: The hook event carrying the submitted prompt.

    Returns:
        The thinking state and the prompt to show.
    """
    return "Thinking", {"prompt": input_data.get("prompt", "Processing...")}


def ready_telemetry(_input_data: dict[str, Any]) -> Telemetry:
    """Translate the end of an agent turn into an idle state.

    Returns:
        The idle state and a ready status.
    """
    return "Idle", {"status": "Ready"}


def stop_telemetry(input_data: dict[str, Any]) -> Telemetry:
    """Publish the final assistant message with the idle state.

    Args:
        input_data: The hook event carrying the last assistant message.

    Returns:
        The idle state, with the final message when the event reports one.
    """
    state, details = ready_telemetry(input_data)
    message = message_text(input_data.get("last_assistant_message"))
    if message is not None:
        details["message"] = message
    return state, details


def permission_request_telemetry(input_data: dict[str, Any]) -> Telemetry:
    """Translate a tool permission request into a waiting state.

    Args:
        input_data: The hook event describing the tool awaiting permission.

    Returns:
        The waiting state, the tool details, and the prompt to show.
    """
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

    Args:
        input_data: The hook event naming how the session started.

    Returns:
        The idle state and a status for the source, or ``None`` after compaction.
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
    """Translate SessionEnd using an agent's reason statuses, never raw reasons.

    A documented reason is also published as ``end_reason``, which the
    dashboard reads instead of the display status: it removes the card of a
    session ended by ``clear``, since the agent continues under a new session.

    Args:
        input_data: The hook event naming why the session ended.
        statuses: Status to publish, keyed by the agent's documented reasons.

    Returns:
        The idle state, a status for the reason, and the reason if documented.
    """
    reason = input_data.get("reason")
    if isinstance(reason, str) and reason in statuses:
        return "Idle", {"status": statuses[reason], "end_reason": reason}
    return "Idle", {"status": "session ended"}


def subagent_start_telemetry(input_data: dict[str, Any]) -> Telemetry:
    """Report a starting subagent as the Agent tool running its agent type.

    Args:
        input_data: The hook event naming the subagent's type.

    Returns:
        The acting state and the Agent tool details.
    """
    details: dict[str, Any] = {"tool": "Agent"}
    agent_type = input_data.get("agent_type")
    if isinstance(agent_type, str) and agent_type:
        details["cmd"] = agent_type
    return "Acting", details


def is_subagent_event(input_data: dict[str, Any]) -> bool:
    """Return whether an event fired inside a subagent, not the main thread.

    Args:
        input_data: The hook event to inspect.

    Returns:
        Whether the event carries a subagent's identifier.
    """
    return isinstance(input_data.get("agent_id"), str)


def pre_compact_telemetry(input_data: dict[str, Any]) -> Telemetry | None:
    """Translate main-thread PreCompact, naming a documented trigger.

    Args:
        input_data: The hook event naming what triggered compaction.

    Returns:
        The thinking state and a compaction status, or ``None`` for a subagent.
    """
    if is_subagent_event(input_data):
        return None
    trigger = input_data.get("trigger")
    status = "Compacting context"
    if trigger in _COMPACTION_TRIGGERS:
        status = f"{status} ({trigger})"
    return "Thinking", {"status": status}


def post_compact_telemetry(input_data: dict[str, Any]) -> Telemetry | None:
    """Translate main-thread PostCompact.

    Manual compaction returns to the prompt; automatic compaction resumes work.

    Args:
        input_data: The hook event naming what triggered compaction.

    Returns:
        The state to resume in and a compacted status, or ``None`` for a subagent.
    """
    if is_subagent_event(input_data):
        return None
    state = "Idle" if input_data.get("trigger") == "manual" else "Thinking"
    return state, {"status": "Context compacted"}


def pre_tool_telemetry(
    input_data: dict[str, Any],
    *,
    agent: str,
    question_tool: str,
    command_fields: Mapping[str, str],
) -> Telemetry:
    """Translate an event for a tool about to run, keyed by its tool-use ID.

    Args:
        input_data: The hook event naming the tool about to run.
        agent: The agent whose start times are recorded.
        question_tool: The tool that asks the user a question.
        command_fields: Input field holding the command, per tool name.

    Returns:
        The waiting state for the question tool, otherwise the acting state and
        the tool details.
    """
    if input_data.get("tool_name") == question_tool:
        return "Waiting for Input", {
            "prompt": question_prompt(input_data.get("tool_input"))
        }
    if (identity := tool_use_identity(input_data)) is not None:
        record_tool_start(agent, identity)
    return "Acting", tool_details(input_data, command_fields)


def tool_result_telemetry(
    input_data: dict[str, Any],
    outcome: tuple[str, str, str | None],
    duration: float | None,
) -> Telemetry:
    """Build the telemetry for a finished tool call.

    Args:
        input_data: The hook event naming the tool.
        outcome: The state, the status to show, and an error message or ``None``.
        duration: The call's duration in seconds, or ``None`` when unknown.

    Returns:
        The state, with the tool details, status, error, and duration.
    """
    state, status, error = outcome
    details = {**tool_details(input_data, {}), "status": status}
    if error is not None:
        details["error"] = error
    if duration is not None:
        details["duration"] = duration
    return state, details
