# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Stable session identity resolution for built-in hooks."""

import hashlib
import os
from collections.abc import Mapping
from typing import Any

from vauxhall.core.telemetry import MAX_SESSION_ID_LENGTH


def _non_empty_string(value: object) -> str | None:
    """Return a stripped non-empty string.

    Args:
        value: The candidate value.

    Returns:
        The stripped string, or ``None`` when it is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _publishable(source: str, identifier: str) -> str:
    """Prefix an identifier with its source, hashing it if too long to publish.

    Truncating instead could give two sessions the same identity. The digest
    form uses ``<source>-sha256:`` so it can't equal a short identifier's
    ``<source>:<identifier>``.

    Args:
        source: The source the identifier came from.
        identifier: The identifier.

    Returns:
        ``<source>:<identifier>``, or ``<source>-sha256:<digest>`` when that
        exceeds the telemetry limit.
    """
    session_id = f"{source}:{identifier}"
    if len(session_id) <= MAX_SESSION_ID_LENGTH:
        return session_id
    # Hook input is JSON, which can carry a lone surrogate.
    digest = hashlib.sha256(identifier.encode(errors="surrogatepass")).hexdigest()
    return f"{source}-sha256:{digest}"


def resolve_session_id(
    input_data: dict[str, Any],
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve one stable opaque session identifier from hook context.

    Args:
        input_data: The hook event, checked for a native or transcript identity.
        environment: Environment to read ``VAUXHALL_SESSION_ID`` from, defaulting
            to the process environment.

    Returns:
        A prefixed identifier naming the source it came from, or ``None`` when
        no source identifies the session.
    """
    native_id = _non_empty_string(input_data.get("session_id"))
    if native_id is not None:
        return _publishable("native", native_id)
    transcript_path = _non_empty_string(input_data.get("transcript_path"))
    if transcript_path is not None:
        digest = hashlib.sha256(transcript_path.encode()).hexdigest()
        return f"transcript:{digest}"
    source = os.environ if environment is None else environment
    configured_id = _non_empty_string(source.get("VAUXHALL_SESSION_ID"))
    if configured_id is not None:
        return _publishable("environment", configured_id)
    return None
