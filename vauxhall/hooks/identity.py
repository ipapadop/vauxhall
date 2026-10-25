# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Stable session and workspace identity for built-in hooks."""

import hashlib
import os
from collections.abc import Mapping
from typing import Any

from vauxhall.core.telemetry import MAX_SESSION_ID_LENGTH, MAX_WORKSPACE_LENGTH

# A card shows only two lines of its workspace, so a shortened workspace stays
# short enough for its start, end, and digest to show.
_WORKSPACE_HEAD_LENGTH = 24
_WORKSPACE_TAIL_LENGTH = 48
_WORKSPACE_DIGEST_LENGTH = 16


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


def _sha256(text: str) -> str:
    """Return the SHA-256 hex digest of text.

    Args:
        text: The text to hash. Hook input is JSON, which can carry a lone
            surrogate, so surrogates are encoded rather than rejected.

    Returns:
        The hex digest.
    """
    return hashlib.sha256(text.encode(errors="surrogatepass")).hexdigest()


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
    return f"{source}-sha256:{_sha256(identifier)}"


def publishable_workspace(workspace: str) -> str:
    """Shorten a workspace path too long to publish, keeping it distinct.

    The workspace is part of a card's identity, so the shortened form keeps
    the path's start (which decides the LOCAL or REMOTE badge) and end (its
    most specific part) and appends a digest of the whole path, which keeps
    paths that differ only in the middle apart.

    Args:
        workspace: The workspace path.

    Returns:
        The path, or ``<start>…<end> [sha256:<digest>]``, 99 characters, when
        it exceeds the telemetry limit.
    """
    if len(workspace) <= MAX_WORKSPACE_LENGTH:
        return workspace
    head = workspace[:_WORKSPACE_HEAD_LENGTH]
    tail = workspace[-_WORKSPACE_TAIL_LENGTH:]
    digest = _sha256(workspace)[:_WORKSPACE_DIGEST_LENGTH]
    return f"{head}…{tail} [sha256:{digest}]"


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
        return f"transcript:{_sha256(transcript_path)}"
    source = os.environ if environment is None else environment
    configured_id = _non_empty_string(source.get("VAUXHALL_SESSION_ID"))
    if configured_id is not None:
        return _publishable("environment", configured_id)
    return None
