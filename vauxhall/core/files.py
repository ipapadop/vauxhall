# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Atomic file replacement shared by the dashboard and hooks.

Hooks import this module on every event, so it imports only modules a hook
loads anyway.
"""

import json
import os
import stat
from pathlib import Path
from typing import Any

# The system temporary directory is shared, so a name another account could
# pre-create is opened without following a symlink into somewhere it owns.
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def write_atomically(
    path: Path,
    text: str,
    *,
    private: bool = False,
    durable: bool = True,
    follow_symlinks: bool = False,
) -> None:
    """Replace a file so readers see either the old or the new text.

    Writers can run in separate processes, so the temporary file has a unique
    name: a fixed one would let two writers interleave in it.

    Args:
        path: The file to replace.
        text: Its new contents.
        private: Create the file readable by its owner alone. Otherwise it
            keeps an existing file's mode, or gets the umask's default.
        durable: Flush the contents to disk before replacing the file. Hooks
            skip this for scratch files they can lose, since an agent waits
            for each hook.
        follow_symlinks: Replace a symlink's target, in the target's
            directory, and keep the link, instead of replacing the link. Pass
            it only for paths the user controls, never for a workspace file
            a cloned repository could point elsewhere.

    Raises:
        OSError: If the file cannot be written.
    """
    if follow_symlinks:
        # Unlike Path.resolve, realpath never raises, even on a symlink loop.
        path = Path(os.path.realpath(path))
    temporary = path.with_name(f".{path.name}.{os.urandom(8).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600 if private else 0o666)
    try:
        # Hook input is JSON, which can carry a lone surrogate.
        with os.fdopen(
            descriptor, "w", encoding="utf-8", errors="surrogatepass"
        ) as handle:
            handle.write(text)
            if durable:
                handle.flush()
                os.fsync(handle.fileno())
        if not private and path.exists():
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_json_atomically(
    path: Path, data: dict[str, Any], *, follow_symlinks: bool = False
) -> None:
    """Replace a JSON file durably, keeping its mode.

    Args:
        path: The file to replace.
        data: The data to serialize into it.
        follow_symlinks: Passed to ``write_atomically``.
    """
    write_atomically(
        path, json.dumps(data, indent=2) + "\n", follow_symlinks=follow_symlinks
    )
