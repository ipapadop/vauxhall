# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Shared telemetry protocol constants and validation."""

from typing import Any, Final

SCHEMA_VERSION: Final = 1
REQUIRED_STRING_FIELDS: Final = ("agent", "workspace", "session_id", "state")
SUPPORTED_STATES = frozenset(
    {"Acting", "Thinking", "Waiting for Input", "Input Required", "Error", "Idle"}
)
_ALLOWED_FIELDS = frozenset(
    {"schema_version", "agent", "workspace", "session_id", "state", "env", "details"}
)
_IDENTITY_FIELD_LIMITS = {
    "agent": 128,
    "workspace": 4096,
    "session_id": 256,
    "state": 32,
    "env": 16,
}
_MAX_DETAIL_COUNT = 16
_MAX_DETAIL_KEY_LENGTH = 64
_MAX_DETAIL_STRING_LENGTH = 4096
_NUMERIC_DETAIL_FIELDS = frozenset({"tokens", "duration"})


def _is_valid_details(details: object) -> bool:
    """Return whether details matches the bounded scalar-value schema.

    Args:
        details: The candidate details mapping.

    Returns:
        Whether the details are a mapping of bounded keys to scalar values.
    """
    if not isinstance(details, dict) or len(details) > _MAX_DETAIL_COUNT:
        return False
    for key, value in details.items():
        if not isinstance(key, str) or len(key) > _MAX_DETAIL_KEY_LENGTH:
            return False
        if isinstance(value, str):
            if len(value) > _MAX_DETAIL_STRING_LENGTH:
                return False
        elif not isinstance(value, (int, float, bool)) and value is not None:
            return False
        if key in _NUMERIC_DETAIL_FIELDS and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            return False
    return True


def _identity_validation_error(payload: dict[str, Any]) -> str | None:
    """Validate bounded identity fields without exposing their values.

    Args:
        payload: The telemetry payload to check.

    Returns:
        A reason naming only the offending field, or ``None`` when the identity
        fields are valid.
    """
    for field in REQUIRED_STRING_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"{field} must be a non-empty string"
    for field, limit in _IDENTITY_FIELD_LIMITS.items():
        if field == "env" and field not in payload:
            continue
        value = payload.get(field)
        if not isinstance(value, str) or not 0 < len(value) <= limit:
            return f"{field} must be a string of 1..{limit} characters"
    if payload["state"] not in SUPPORTED_STATES:
        return "state must be a supported telemetry state"
    if "env" in payload and payload["env"] not in {"local", "remote"}:
        return "env must be local or remote"
    return None


def telemetry_validation_error(payload: object) -> str | None:  # noqa: PLR0911
    """Return a safe rejection reason, or None for valid schema-v1 telemetry.

    Args:
        payload: The candidate telemetry payload.

    Returns:
        A reason that never repeats the payload's values, or ``None`` when the
        payload is valid.
    """
    if not isinstance(payload, dict):
        return "telemetry payload must be a JSON object"
    if "schema_version" not in payload:
        return "schema_version is required"
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        return f"unsupported schema_version; expected {SCHEMA_VERSION}"
    identity_error = _identity_validation_error(payload)
    if identity_error is not None:
        return identity_error
    if set(payload) - _ALLOWED_FIELDS:
        return "telemetry payload contains unsupported fields"
    if not _is_valid_details(payload.get("details", {})):
        return (
            "details must contain at most 16 scalar entries "
            "with bounded keys and values"
        )
    return None


def validate_telemetry(data: object) -> dict[str, Any] | None:
    """Return a shallow copy of valid schema-v1 telemetry, or None.

    Args:
        data: The candidate telemetry payload.

    Returns:
        A shallow copy of the payload, or ``None`` when it is invalid.
    """
    if telemetry_validation_error(data) is not None:
        return None
    assert isinstance(data, dict)
    return dict(data)
