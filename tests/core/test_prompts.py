# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the prompt protocol shared by the dashboard and the relay."""

import json

import pytest

from vauxhall.core.prompts import (
    MAX_MESSAGE_BYTES,
    MAX_PROMPT_LENGTH,
    PROMPT_KIND,
    format_ack,
    format_prompt,
    parse_ack,
    parse_prompt,
    parse_session_topic,
    prompt_text_error,
    session_topic,
)


def test_session_topic_encodes_reserved_characters() -> None:
    """A session identity with MQTT wildcards or separators stays one topic level."""
    topic = session_topic("Codex", "native:a/b+c#d", PROMPT_KIND)

    assert topic == "vauxhall/agents/codex/sessions/native%3Aa%2Fb%2Bc%23d/prompt"
    assert parse_session_topic(topic) == ("codex", "native:a/b+c#d", PROMPT_KIND)


@pytest.mark.parametrize(
    "topic",
    [
        "vauxhall/agents/codex/activity",
        "vauxhall/agents/codex/sessions/one/other",
        "vauxhall/agents/codex/sessions//prompt",
    ],
)
def test_parse_session_topic_rejects_other_topics(topic: str) -> None:
    """Only per-session prompt and acknowledgment topics are recognized.

    Args:
        topic: A topic that is not a per-session one.
    """
    assert parse_session_topic(topic) is None


@pytest.mark.parametrize("text", ["two\nlines\tand a tab", "é 日本語"])
def test_prompt_text_accepts_ordinary_text(text: str) -> None:
    """Multiline, tabbed, and non-ASCII text is a valid prompt.

    Args:
        text: An acceptable prompt.
    """
    assert prompt_text_error(text) is None


@pytest.mark.parametrize(
    "text",
    [
        None,
        "   \n",
        "x" * (MAX_PROMPT_LENGTH + 1),
        "before\x1b[201~after",
        "delete\x7f",
        "c1\x9b",
        "lone\ud800surrogate",
    ],
)
def test_prompt_text_rejects_unsafe_text(text: object) -> None:
    """Empty, oversized, or control-character text is refused.

    An escape could end the terminal's bracketed paste early, and DEL and the C1
    controls sit at the edges of the rejected ranges.

    Args:
        text: An unacceptable prompt.
    """
    assert prompt_text_error(text) is not None


def test_prompt_round_trips() -> None:
    """A formatted prompt parses back to its identifier and text."""
    payload = format_prompt("abc", "run the tests\nplease")

    assert parse_prompt(payload.encode()) == ("abc", "run the tests\nplease")


@pytest.mark.parametrize("character", ["é", "日", "😀", '"', "a\n"])
def test_longest_prompt_fits_in_a_message(character: str) -> None:
    """A prompt at the character limit is never larger than the relay accepts.

    Args:
        character: The character the prompt repeats, chosen for its encoded size.
    """
    text = (character * MAX_PROMPT_LENGTH)[:MAX_PROMPT_LENGTH]
    payload = format_prompt("a" * 64, text).encode()

    assert len(payload) <= MAX_MESSAGE_BYTES
    assert parse_prompt(payload) == ("a" * 64, text)


def test_format_prompt_rejects_invalid_input() -> None:
    """A prompt with a bad identifier or text is not encoded."""
    with pytest.raises(ValueError, match="id"):
        format_prompt("", "hello")
    with pytest.raises(ValueError, match="control"):
        format_prompt("abc", "\x1b")


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        json.dumps({"id": "a", "text": "x"}).encode(),
        json.dumps({"schema_version": 1, "id": "", "text": "x"}).encode(),
        json.dumps({"schema_version": 1, "id": "a", "text": "\x1b"}).encode(),
        json.dumps(
            {"schema_version": 1, "id": "a", "text": "x" * MAX_MESSAGE_BYTES}
        ).encode(),
    ],
)
def test_parse_prompt_rejects_invalid_messages(payload: bytes) -> None:
    """Malformed, unversioned, or unsafe prompt messages are dropped.

    Args:
        payload: A payload that is not a valid prompt.
    """
    assert parse_prompt(payload) is None


def test_ack_round_trips() -> None:
    """An acknowledgment keeps its status and failure reason."""
    assert parse_ack(format_ack("abc", "delivered").encode()) == {
        "id": "abc",
        "status": "delivered",
    }
    assert parse_ack(format_ack("abc", "failed", "pane-unavailable").encode()) == {
        "id": "abc",
        "status": "failed",
        "reason": "pane-unavailable",
    }


def test_format_ack_rejects_invalid_input() -> None:
    """An acknowledgment with a bad identifier, status, or reason is not encoded."""
    with pytest.raises(ValueError, match="id"):
        format_ack("", "delivered")
    with pytest.raises(ValueError, match="status"):
        format_ack("abc", "maybe")
    with pytest.raises(ValueError, match="reason"):
        format_ack("abc", "failed", "because")


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        json.dumps({"schema_version": 1, "id": "a", "status": "maybe"}).encode(),
        json.dumps({"schema_version": 1, "id": 1, "status": "delivered"}).encode(),
        json.dumps(
            {"schema_version": 1, "id": "a", "status": "failed", "reason": "x"}
        ).encode(),
        b" " * (MAX_MESSAGE_BYTES + 1),
    ],
)
def test_parse_ack_rejects_invalid_messages(payload: bytes) -> None:
    """Malformed or unknown acknowledgments are dropped.

    Args:
        payload: A payload that is not a valid acknowledgment.
    """
    assert parse_ack(payload) is None
