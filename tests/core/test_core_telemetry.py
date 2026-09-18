# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the telemetry protocol contract."""

import pytest

from vauxhall.core.telemetry import (
    SCHEMA_VERSION,
    telemetry_validation_error,
    validate_telemetry,
)


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
    """Invalid protocol payloads return safe reason-only errors.

    Args:
        payload: The case's payload.
        expected_error: The error message the case expects.
    """
    assert telemetry_validation_error(payload) == expected_error


def valid_event(**overrides: object) -> dict[str, object]:
    """Return a valid version-one dashboard telemetry event.

    Returns:
        The event.
    """
    event: dict[str, object] = {
        "schema_version": 1,
        "agent": "Codex",
        "workspace": "/workspace",
        "session_id": "session-1",
        "state": "Thinking",
        "details": {},
    }
    event.update(overrides)
    return event


@pytest.mark.parametrize("payload", [None, [], "telemetry", 1])
def test_telemetry_rejects_non_object_payloads(payload: object) -> None:
    """Reject JSON values that cannot represent telemetry objects.

    Args:
        payload: The case's payload.
    """
    assert validate_telemetry(payload) is None


@pytest.mark.parametrize(
    "field", ["schema_version", "agent", "workspace", "session_id", "state"]
)
def test_telemetry_rejects_missing_required_fields(field: str) -> None:
    """Reject events missing any required schema field.

    Args:
        field: The configuration field under test.
    """
    event = valid_event()
    del event[field]

    assert validate_telemetry(event) is None


def test_telemetry_accepts_omitted_optional_details() -> None:
    """Accept a telemetry event containing only the required fields."""
    event = valid_event()
    del event["details"]

    assert validate_telemetry(event) == event


def test_telemetry_rejects_unknown_top_level_fields() -> None:
    """Reject unversioned top-level additions to the version-one schema."""
    assert validate_telemetry(valid_event(extra={"nested": "value"})) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("schema_version", 2),
        ("agent", 1),
        ("agent", " "),
        ("workspace", []),
        ("workspace", "\t"),
        ("session_id", None),
        ("session_id", "\n"),
        ("state", False),
        ("details", []),
        ("env", 1),
    ],
)
def test_telemetry_rejects_wrong_field_types(field: str, value: object) -> None:
    """Reject events whose declared fields have the wrong types.

    Args:
        field: The configuration field under test.
        value: The case's value.
    """
    assert validate_telemetry(valid_event(**{field: value})) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent", "a" * 129),
        ("workspace", "w" * 4097),
        ("session_id", "s" * 257),
        ("state", "x" * 33),
        ("env", "e" * 17),
    ],
)
def test_telemetry_rejects_oversized_identity_fields(field: str, value: str) -> None:
    """Reject identity fields that exceed their locked limits.

    Args:
        field: The configuration field under test.
        value: The case's value.
    """
    assert validate_telemetry(valid_event(**{field: value})) is None


@pytest.mark.parametrize("state", ["Running", "Unknown", "thinking", ""])
def test_telemetry_rejects_unsupported_or_empty_states(state: str) -> None:
    """Reject states outside the dashboard's fixed state vocabulary.

    Args:
        state: The case's telemetry state.
    """
    assert validate_telemetry(valid_event(state=state)) is None


@pytest.mark.parametrize("env", ["LOCAL", "staging", ""])
def test_telemetry_rejects_unsupported_environments(env: str) -> None:
    """Reject environments outside the local and remote values.

    Args:
        env: The case's environment name.
    """
    assert validate_telemetry(valid_event(env=env)) is None


def test_telemetry_rejects_invalid_details() -> None:
    """Reject details that exceed shape, key, value, or metric constraints."""
    assert (
        validate_telemetry(valid_event(details={str(i): i for i in range(17)})) is None
    )
    assert validate_telemetry(valid_event(details={"k" * 65: "value"})) is None
    assert validate_telemetry(valid_event(details={"status": "x" * 4097})) is None
    assert validate_telemetry(valid_event(details={"nested": {"value": 1}})) is None
    assert validate_telemetry(valid_event(details={"items": [1]})) is None
    assert validate_telemetry(valid_event(details={"tokens": True})) is None
    assert validate_telemetry(valid_event(details={"duration": True})) is None


def test_telemetry_accepts_exact_field_boundaries() -> None:
    """Accept valid telemetry at every locked size boundary."""
    event = valid_event(
        agent="a" * 128,
        workspace="w" * 4096,
        session_id="s" * 256,
        state="Waiting for Input",
        env="remote",
        details={
            "k" * 64: "v" * 4096,
            "tokens": 1234,
            "duration": 2.5,
            "enabled": True,
            "empty": None,
        },
    )

    assert validate_telemetry(event) == event

    event["details"] = {str(i): i for i in range(16)}
    assert validate_telemetry(event) == event


def test_telemetry_returns_a_shallow_copy() -> None:
    """Prevent later top-level decoded-payload mutations from changing events."""
    event = valid_event()

    validated = validate_telemetry(event)

    assert validated is not None
    event["agent"] = "mutated"
    assert validated["agent"] == "Codex"
