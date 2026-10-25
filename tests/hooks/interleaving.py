# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Run a second hook's work in the middle of a first one's file write."""

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def after_first_write_open(action: Callable[[], object]) -> Iterator[None]:
    """Run an action once, right after the first file opened for writing.

    The action stands in for another hook process that runs while this one
    holds the file open, so a race shows up without relying on thread timing.

    Args:
        action: What the concurrent hook process does.

    Yields:
        Nothing; the patch is active inside the ``with`` block.
    """
    real_open = os.open
    pending = [action]

    def open_then_act(
        path: str | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        descriptor = real_open(path, flags, mode)
        if flags & os.O_WRONLY and pending:
            pending.pop()()
        return descriptor

    with patch.object(os, "open", open_then_act):
        yield
