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
    A details key that repeats a top-level field would make the two
    indistinguishable, so it fails the test when the block exits; raising it
    inside the hook would be swallowed by ``run_hook``.

    Yields:
        The mock that records the events.
    """
    published = MagicMock()
    collisions: set[str] = set()

    def publish(events: Iterable[Mapping[str, Any]], *_: object) -> bool:
        for event in events:
            fields = {key: value for key, value in event.items() if key != "details"}
            details = event.get("details", {})
            collisions.update(fields.keys() & details.keys())
            published(**fields, **{k: v for k, v in details.items() if k not in fields})
        return True

    with patch("vauxhall.hooks.client.publish", publish):
        yield published
    assert not collisions, f"details repeat top-level fields: {sorted(collisions)}"
