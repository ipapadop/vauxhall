# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Stable session identity resolution for built-in hooks."""

import hashlib
import os
from collections.abc import Mapping
from typing import Any


def _non_empty_string(value: object) -> str | None:
    """Return a stripped non-empty string."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def resolve_session_id(
    input_data: dict[str, Any],
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve one stable opaque session identifier from hook context."""
    native_id = _non_empty_string(input_data.get("session_id"))
    if native_id is not None:
        return f"native:{native_id}"
    transcript_path = _non_empty_string(input_data.get("transcript_path"))
    if transcript_path is not None:
        digest = hashlib.sha256(transcript_path.encode()).hexdigest()
        return f"transcript:{digest}"
    source = os.environ if environment is None else environment
    configured_id = _non_empty_string(source.get("VAUXHALL_SESSION_ID"))
    if configured_id is not None:
        return f"environment:{configured_id}"
    return None
