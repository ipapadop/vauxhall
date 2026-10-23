# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""A recorder for the telemetry the hooks publish."""

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch


@contextmanager
def record_published() -> Iterator[MagicMock]:
    """Replace the hooks' publisher with one that records every event.

    Each event becomes one call of the yielded mock, with the event's fields
    and its details as keyword arguments, so assertions name fields directly.

    Yields:
        The mock that records the events.
    """
    published = MagicMock()

    def publish(events: Iterable[Mapping[str, Any]], *_: object) -> bool:
        for event in events:
            fields = {key: value for key, value in event.items() if key != "details"}
            published(**fields, **event.get("details", {}))
        return True

    with patch("vauxhall.hooks.client.publish", publish):
        yield published
