# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for stable built-in hook session identity."""

import pytest

from vauxhall.core.telemetry import MAX_SESSION_ID_LENGTH
from vauxhall.hooks.identity import resolve_session_id


@pytest.mark.parametrize(
    ("event", "environment", "expected"),
    [
        (
            {"session_id": " session-123 ", "transcript_path": "/ignored"},
            {"VAUXHALL_SESSION_ID": "ignored"},
            "native:session-123",
        ),
        (
            {"transcript_path": "/workspace/transcript.jsonl"},
            {"VAUXHALL_SESSION_ID": "ignored"},
            (
                "transcript:"
                "91e1cc1d33c76e7bdc99ea5682adbad45f9b5c456fece1e274f85c5eece46c3f"
            ),
        ),
        ({}, {"VAUXHALL_SESSION_ID": " external-1 "}, "environment:external-1"),
        ({"session_id": " ", "transcript_path": ""}, {}, None),
    ],
)
def test_resolve_session_id_uses_stable_fallback_order(
    event: dict, environment: dict[str, str], expected: str | None
) -> None:
    """Use native, transcript, and environment identities in stable order.

    Args:
        event: The case's event name.
        environment: The case's environment mapping.
        expected: The result the case expects.
    """
    assert resolve_session_id(event, environment) == expected


@pytest.mark.parametrize(
    ("input_data", "environment", "prefix"),
    [
        ({"session_id": "x" * 300}, {}, "native"),
        ({}, {"VAUXHALL_SESSION_ID": "x" * 300}, "environment"),
    ],
)
def test_resolve_session_id_hashes_an_identifier_too_long_to_publish(
    input_data: dict[str, str], environment: dict[str, str], prefix: str
) -> None:
    """An identifier over the telemetry limit becomes a stable digest.

    Truncating it could give two sessions the same identity.

    Args:
        input_data: The case's hook event.
        environment: The case's environment.
        prefix: The source prefix the identity keeps.
    """
    session_id = resolve_session_id(input_data, environment)
    other = resolve_session_id(
        {key: value + "y" for key, value in input_data.items()},
        {key: value + "y" for key, value in environment.items()},
    )

    assert session_id is not None
    assert len(session_id) <= MAX_SESSION_ID_LENGTH
    assert session_id.startswith(prefix + "-sha256:")
    assert session_id == resolve_session_id(input_data, environment)
    assert other != session_id


def test_resolve_session_id_keeps_an_identifier_at_the_limit() -> None:
    """Only identifiers that would be rejected change."""
    native_id = "x" * (MAX_SESSION_ID_LENGTH - len("native:"))

    assert resolve_session_id({"session_id": native_id}, {}) == f"native:{native_id}"


def test_resolve_session_id_hashes_a_long_identifier_with_a_lone_surrogate() -> None:
    """JSON hook input can decode to a lone surrogate, which UTF-8 rejects."""
    session_id = resolve_session_id({"session_id": "\ud800" + "x" * 300}, {})

    assert session_id is not None
    assert session_id.startswith("native-sha256:")


def test_resolve_session_id_digest_differs_from_a_short_identifier() -> None:
    """A short ID that spells a digest can't share a long ID's session."""
    long_id = resolve_session_id({"session_id": "x" * 300}, {})
    assert long_id is not None
    digest = long_id.rsplit(":", 1)[1]

    assert resolve_session_id({"session_id": f"sha256:{digest}"}, {}) != long_id


def test_resolve_session_id_hashes_a_transcript_path_with_a_lone_surrogate() -> None:
    """A transcript path from JSON input can hold a lone surrogate."""
    session_id = resolve_session_id({"transcript_path": "/t/\ud800"}, {})

    assert session_id is not None
    assert session_id.startswith("transcript:")
