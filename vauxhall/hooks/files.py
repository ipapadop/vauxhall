# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""File housekeeping shared by the hook helpers."""

import os
import time
from contextlib import suppress
from pathlib import Path

# The system temporary directory is shared, so a name another account could
# pre-create is opened without following a symlink into somewhere it owns.
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def remove_old_files(directory: Path, pattern: str, max_age_seconds: float) -> None:
    """Remove files not modified for longer than an age, ignoring failures.

    Args:
        directory: The directory to sweep.
        pattern: Glob pattern of the files to consider.
        max_age_seconds: Age past which a file is removed.
    """
    cutoff = time.time() - max_age_seconds
    with suppress(OSError):
        for path in directory.glob(pattern):
            with suppress(OSError):
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)


def write_atomically(path: Path, text: str) -> None:
    """Replace a private file so readers see either the old or the new text.

    Hooks run as separate processes, so the temporary file has a unique name:
    a fixed one would let two writers interleave in it.

    Args:
        path: The file to replace.
        text: Its new contents.

    Raises:
        OSError: If the file cannot be written.
    """
    temporary = path.with_name(f".{path.name}.{os.urandom(8).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


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
