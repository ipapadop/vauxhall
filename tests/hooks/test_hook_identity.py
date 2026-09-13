# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for stable built-in hook session identity."""

import pytest

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
    """Use native, transcript, and environment identities in stable order."""
    assert resolve_session_id(event, environment) == expected
