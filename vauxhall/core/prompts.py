# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Shared protocol for sending prompts from the dashboard to agent sessions."""

import json
from typing import Any, Final, TypeGuard
from urllib.parse import quote, unquote

PROMPT_SCHEMA_VERSION: Final = 1
MAX_PROMPT_LENGTH: Final = 4096
MAX_MESSAGE_BYTES: Final = 16384
PROMPT_KIND: Final = "prompt"
ACK_KIND: Final = "ack"
PROMPT_TOPIC_FILTER: Final = "vauxhall/agents/+/sessions/+/prompt"
ACK_TOPIC_FILTER: Final = "vauxhall/agents/+/sessions/+/ack"
ACK_STATUSES: Final = frozenset({"delivered", "failed"})
FAILURE_REASONS: Final = frozenset({"pane-unavailable", "delivery-failed"})
_MAX_ID_LENGTH = 64
_ALLOWED_CONTROLS = frozenset("\n\t")


def session_topic(agent: str, session_id: str, kind: str) -> str:
    """Build the per-session topic that carries prompts or their acknowledgments.

    Args:
        agent: The agent name, lower-cased like the activity topic.
        session_id: The session identity from telemetry, which may contain
            characters MQTT reserves, so it is percent-encoded.
        kind: ``PROMPT_KIND`` or ``ACK_KIND``.

    Returns:
        The topic, ``vauxhall/agents/<agent>/sessions/<session>/<kind>``.
    """
    return (
        f"vauxhall/agents/{quote(agent.lower(), safe='')}"
        f"/sessions/{quote(session_id, safe='')}/{kind}"
    )


def parse_session_topic(topic: str) -> tuple[str, str, str] | None:
    """Split a per-session topic into its parts.

    Args:
        topic: The topic a message arrived on.

    Returns:
        The agent (lower-case), session identity, and kind, or ``None`` when
        the topic is not a per-session topic.
    """
    parts = topic.split("/")
    if len(parts) != 6 or parts[:2] != ["vauxhall", "agents"] or parts[3] != "sessions":
        return None
    if parts[5] not in {PROMPT_KIND, ACK_KIND} or not parts[2] or not parts[4]:
        return None
    return unquote(parts[2]), unquote(parts[4]), parts[5]


def prompt_text_error(text: object) -> str | None:
    """Explain why text cannot be sent to an agent, without echoing it.

    Control characters other than newline and tab are rejected: a raw escape
    could end the terminal's bracketed paste early and have the rest typed as
    keystrokes.

    Args:
        text: The candidate prompt.

    Returns:
        A reason, or ``None`` when the text is acceptable.
    """
    if not isinstance(text, str) or not text.strip():
        return "Prompt must not be empty"
    if len(text) > MAX_PROMPT_LENGTH:
        return f"Prompt must be at most {MAX_PROMPT_LENGTH} characters"
    if any(
        (ord(char) < 32 or 127 <= ord(char) < 160) and char not in _ALLOWED_CONTROLS
        for char in text
    ):
        return "Prompt must not contain control characters"
    return None


def _is_message_id(value: object) -> TypeGuard[str]:
    """Return whether a value is a usable message identifier.

    Args:
        value: The candidate identifier.

    Returns:
        Whether it is a non-empty string of bounded length.
    """
    return isinstance(value, str) and 0 < len(value) <= _MAX_ID_LENGTH


def format_prompt(message_id: str, text: str) -> str:
    """Encode a prompt message.

    Args:
        message_id: Identifier the acknowledgment refers back to.
        text: The prompt text.

    Returns:
        The JSON payload.

    Raises:
        ValueError: If the identifier or text is not acceptable.
    """
    if not _is_message_id(message_id):
        message = "id must be a string of 1..64 characters"
        raise ValueError(message)
    if (error := prompt_text_error(text)) is not None:
        raise ValueError(error)
    return json.dumps(
        {"schema_version": PROMPT_SCHEMA_VERSION, "id": message_id, "text": text}
    )


def parse_prompt(payload: bytes) -> tuple[str, str] | None:
    """Decode and validate a prompt message.

    Args:
        payload: The raw MQTT payload.

    Returns:
        The message identifier and text, or ``None`` when it is oversized,
        malformed, or invalid.
    """
    if len(payload) > MAX_MESSAGE_BYTES:
        return None
    try:
        data: Any = json.loads(payload.decode())
    except ValueError:
        return None
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != PROMPT_SCHEMA_VERSION
    ):
        return None
    message_id, text = data.get("id"), data.get("text")
    if not _is_message_id(message_id) or not isinstance(text, str):
        return None
    if prompt_text_error(text) is not None:
        return None
    return message_id, text


def format_ack(message_id: str, status: str, reason: str | None = None) -> str:
    """Encode an acknowledgment message.

    Args:
        message_id: The identifier of the prompt being acknowledged.
        status: ``delivered`` or ``failed``.
        reason: For a failure, one of ``FAILURE_REASONS``.

    Returns:
        The JSON payload.

    Raises:
        ValueError: If the identifier, status, or reason is not acceptable.
    """
    if not _is_message_id(message_id):
        message = "id must be a string of 1..64 characters"
        raise ValueError(message)
    if status not in ACK_STATUSES:
        message = "status must be delivered or failed"
        raise ValueError(message)
    if reason is not None and reason not in FAILURE_REASONS:
        message = "reason must be a known failure reason"
        raise ValueError(message)
    payload: dict[str, Any] = {
        "schema_version": PROMPT_SCHEMA_VERSION,
        "id": message_id,
        "status": status,
    }
    if reason is not None:
        payload["reason"] = reason
    return json.dumps(payload)


def parse_ack(payload: bytes) -> dict[str, str] | None:
    """Decode and validate an acknowledgment message.

    Args:
        payload: The raw MQTT payload.

    Returns:
        A dict with ``id``, ``status``, and optionally ``reason``, or ``None``
        when the message is oversized, malformed, or invalid.
    """
    if len(payload) > MAX_MESSAGE_BYTES:
        return None
    try:
        data: Any = json.loads(payload.decode())
    except ValueError:
        return None
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != PROMPT_SCHEMA_VERSION
    ):
        return None
    message_id, status, reason = data.get("id"), data.get("status"), data.get("reason")
    if not _is_message_id(message_id) or status not in ACK_STATUSES:
        return None
    if reason is not None and reason not in FAILURE_REASONS:
        return None
    ack = {"id": message_id, "status": status}
    if reason is not None:
        ack["reason"] = reason
    return ack
