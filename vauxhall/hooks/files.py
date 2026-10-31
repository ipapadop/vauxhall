# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""File housekeeping shared by the hook helpers."""

import os
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


def claim(path: Path) -> Path:
    """Take a file for this process alone by renaming it to a unique name.

    Args:
        path: The file to claim.

    Returns:
        The claimed file's new path; the caller removes it when done.

    Raises:
        OSError: If the file is gone, such as when another process claimed it
            first.
    """
    claimed = path.with_name(f"{path.name}.{os.urandom(8).hex()}.claimed")
    path.rename(claimed)
    # A rename keeps the old modification time, so an age sweep could
    # otherwise remove the file while this process works on it.
    os.utime(claimed)
    return claimed


def unique_name(prefix: str) -> str:
    """Return a file name no other process uses, ordered by creation time.

    Args:
        prefix: The start of the name.

    Returns:
        The prefix, a nanosecond timestamp, and a random suffix.
    """
    return f"{prefix}{time.time_ns():020d}-{os.urandom(8).hex()}"
