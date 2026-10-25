# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""File housekeeping shared by the hook helpers."""

import time
from contextlib import suppress
from pathlib import Path


def remove_old_files(
    directory: Path, pattern: str, max_age_seconds: float, now: float | None = None
) -> None:
    """Remove files not modified for longer than an age, ignoring failures.

    Args:
        directory: The directory to sweep.
        pattern: Glob pattern of the files to consider.
        max_age_seconds: Age past which a file is removed.
        now: The current time, read from the clock when not given.
    """
    cutoff = (time.time() if now is None else now) - max_age_seconds
    with suppress(OSError):
        for path in directory.glob(pattern):
            with suppress(OSError):
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
