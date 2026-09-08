# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Shared telemetry protocol constants and validation."""

from typing import Final

SCHEMA_VERSION: Final = 1
REQUIRED_STRING_FIELDS: Final = ("agent", "workspace", "session_id", "state")


def telemetry_validation_error(payload: object) -> str | None:
    """Return a safe rejection reason, or None for valid schema-v1 telemetry."""
    if not isinstance(payload, dict):
        return "telemetry payload must be a JSON object"
    if "schema_version" not in payload:
        return "schema_version is required"
    if payload["schema_version"] != SCHEMA_VERSION:
        return f"unsupported schema_version; expected {SCHEMA_VERSION}"
    for field in REQUIRED_STRING_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"{field} must be a non-empty string"
    return None
