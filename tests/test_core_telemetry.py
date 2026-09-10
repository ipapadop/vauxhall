# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry protocol contract."""

import pytest

from vauxhall.core.telemetry import SCHEMA_VERSION, telemetry_validation_error


def test_schema_version_one_accepts_required_identity_fields() -> None:
    """Schema-v1 accepts all required identity fields."""
    payload = {
        "schema_version": 1,
        "agent": "Codex",
        "workspace": "/workspace",
        "session_id": "native:session-1",
        "state": "Thinking",
        "details": {},
    }

    assert SCHEMA_VERSION == 1
    assert telemetry_validation_error(payload) is None


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({}, "schema_version is required"),
        (
            {
                "schema_version": 2,
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-1",
                "state": "Thinking",
            },
            "unsupported schema_version; expected 1",
        ),
        (
            {
                "schema_version": True,
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-1",
                "state": "Thinking",
            },
            "unsupported schema_version; expected 1",
        ),
        (
            {
                "schema_version": 1.0,
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "native:session-1",
                "state": "Thinking",
            },
            "unsupported schema_version; expected 1",
        ),
        (
            {
                "schema_version": 1,
                "agent": "Codex",
                "workspace": "/workspace",
                "session_id": "",
                "state": "Thinking",
            },
            "session_id must be a non-empty string",
        ),
    ],
)
def test_invalid_telemetry_returns_reason_only_error(
    payload: object, expected_error: str
) -> None:
    """Invalid protocol payloads return safe reason-only errors."""
    assert telemetry_validation_error(payload) == expected_error
