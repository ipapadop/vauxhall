# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Bound hook text to the telemetry detail limit."""

from vauxhall.core.telemetry import MAX_DETAIL_STRING_LENGTH


def truncate_text(value: str) -> str:
    """Shorten text to the telemetry detail limit, ending it with an ellipsis.

    Args:
        value: The text to bound.

    Returns:
        The text, or its start and an ellipsis when it exceeds the limit.
    """
    if len(value) > MAX_DETAIL_STRING_LENGTH:
        return value[: MAX_DETAIL_STRING_LENGTH - 1] + "…"
    return value


def message_text(value: object) -> str | None:
    """Return nonblank text, such as a message, within the telemetry detail limit.

    Args:
        value: The candidate text.

    Returns:
        The text, truncated with an ellipsis when it exceeds the limit, or
        ``None`` when it is not a non-blank string.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return truncate_text(value)
