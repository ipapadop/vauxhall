# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Per-user scratch files that carry hook state between hook processes.

Each hook event runs in a new process, so streamed message text and tool start
times are kept in files in a private directory under the system temporary
directory. The files are disposable: losing one loses only a message or a
duration.
"""

import hashlib
import json
import os
import stat
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from vauxhall.core.files import NOFOLLOW, write_atomically
from vauxhall.core.logging import get_logger
from vauxhall.core.telemetry import MAX_DETAIL_STRING_LENGTH
from vauxhall.hooks.text import message_text

logger = get_logger(__name__)

# Text from a response that never finished is swept once it cannot belong to a
# live turn, because only a final chunk removes its own file.
_MESSAGE_MAX_AGE_SECONDS = 86400
# Likewise for the start of a tool call that never finished, and for a start
# or claim a killed hook left behind; only finishing a call removes its file.
_TOOL_START_MAX_AGE_SECONDS = 86400
# Timing directories are per user because the system temporary directory is shared.
_USER_SUFFIX = f"-{os.getuid()}" if hasattr(os, "getuid") else ""


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


def _make_private(directory: Path) -> None:
    """Make an owned directory owner-only and remove what others put in it.

    While the directory was reachable, other accounts could add entries, such
    as a symlink where a hook will write; the sticky system temporary
    directory keeps them from replacing the directory itself.

    Args:
        directory: A directory this user owns.

    Raises:
        OSError: If its mode can't be changed.
    """
    directory.chmod(0o700)
    for entry in os.scandir(directory):
        with suppress(OSError):
            if entry.stat(follow_symlinks=False).st_uid != os.getuid():
                Path(entry.path).unlink()
    logger.warning("Made %s private; it was reachable by other accounts", directory)


def private_directory(name: str) -> Path:
    """Return a per-user directory in the system temporary directory.

    The system temporary directory is shared, so another account can pre-create
    the name. A directory that is a symlink or is owned by somebody else is
    rejected rather than used. One this user owns that others can reach, such
    as one created under a permissive umask by an older version, is made
    owner-only.

    Args:
        name: Directory name, to which the user suffix is added.

    Returns:
        The private directory.

    Raises:
        OSError: If the directory is not a private one this user owns.
    """
    directory = Path(tempfile.gettempdir()) / f"{name}{_USER_SUFFIX}"
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    private = stat.S_ISDIR(info.st_mode)
    if hasattr(os, "getuid"):
        # Windows ignores the creation mode, reports every directory as world
        # accessible, and names no owner, so these checks would always fail
        # there. It gives each account its own temporary directory instead.
        private = private and info.st_uid == os.getuid()
        if private and info.st_mode & 0o077:
            _make_private(directory)
    if not private:
        message = f"{directory} is not a private directory"
        # Callers treat OSError as "no state", so say why it is missing.
        logger.warning("%s; remove it to restore hook state", message)
        raise OSError(message)
    return directory


def _hashed_location(name: str, identity: object) -> tuple[Path, str]:
    """Return a private directory and a file name prefix for one identity.

    Args:
        name: The directory name, passed to ``private_directory``.
        identity: Value identifying the files, hashed into the prefix.

    Returns:
        The private directory and the identity's file name prefix.

    Raises:
        OSError: If the directory is not a private one this user owns.
    """
    key = json.dumps(identity, sort_keys=True, default=str)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return private_directory(name), f"{digest}-"


def discard_message_chunks(agent: str, identity: object) -> None:
    """Discard text left by an unfinished model response.

    Args:
        agent: The agent whose message directory is used.
        identity: Value identifying the message.
    """
    with suppress(OSError):
        directory, prefix = _hashed_location(f"vauxhall-messages-{agent}", identity)
        remove_old_files(directory, "*", _MESSAGE_MAX_AGE_SECONDS)
        for path in directory.glob(f"{prefix}*.chunk"):
            path.unlink(missing_ok=True)


def collect_message_chunk(
    agent: str, identity: object, delta: object, *, final: bool
) -> str | None:
    """Collect streamed assistant text and return it when the message ends.

    Each chunk is stored in its own file, because chunk hooks can run at once
    and a shared file would lose one of two concurrent updates. The final
    chunk joins them in the order their hooks stored them. Hooks that run at
    once have no defined order, and a chunk still being stored when the final
    one arrives is left out.

    Args:
        agent: The agent whose message directory is used.
        identity: Value identifying the message across its chunks.
        delta: The chunk's new text; a non-string chunk is ignored.
        final: Whether this chunk ends the message.

    Returns:
        The assembled message when ``final`` is set and text was collected,
        otherwise ``None``.
    """
    if not isinstance(delta, str):
        return None
    try:
        directory, prefix = _hashed_location(f"vauxhall-messages-{agent}", identity)
        remove_old_files(directory, "*", _MESSAGE_MAX_AGE_SECONDS)
        if not final:
            if delta:
                # Text past the detail limit is cut when published anyway.
                text = delta[: MAX_DETAIL_STRING_LENGTH + 1]
                write_atomically(
                    directory / f"{unique_name(prefix)}.chunk",
                    text,
                    private=True,
                    durable=False,
                )
            return None
        parts: list[str] = []
        length = 0
        for path in sorted(directory.glob(f"{prefix}*.chunk")):
            try:
                claimed = claim(path)
            except OSError:
                continue  # Another hook ending or discarding the message took it.
            try:
                # A long response has many chunks; past the limit, only remove them.
                if length <= MAX_DETAIL_STRING_LENGTH:
                    source = os.open(claimed, os.O_RDONLY | NOFOLLOW)
                    with os.fdopen(
                        source, encoding="utf-8", errors="surrogatepass"
                    ) as chunk:
                        parts.append(chunk.read())
                    length += len(parts[-1])
            finally:
                claimed.unlink(missing_ok=True)
        return message_text("".join(parts) + delta)
    except (OSError, UnicodeDecodeError):
        # A partially written chunk must not suppress the event's own telemetry.
        return None


def tool_use_identity(input_data: dict[str, Any]) -> tuple[str, str] | None:
    """Return the session and tool-use IDs that identify one tool call, if any.

    Args:
        input_data: The hook event to read the identity from.

    Returns:
        The session and tool-use IDs, or ``None`` when the event lacks either.
    """
    session_id = input_data.get("session_id")
    tool_use_id = input_data.get("tool_use_id")
    if isinstance(session_id, str) and isinstance(tool_use_id, str):
        return session_id, tool_use_id
    return None


def record_tool_start(agent: str, identity: object) -> None:
    """Record one tool call's start time in its own file.

    Calls that share an identity each get a file; the nanosecond timestamp in the
    name orders them for claim_tool_duration.

    Args:
        agent: The agent whose timing directory is used.
        identity: Value identifying the tool call.
    """
    with suppress(OSError):
        directory, prefix = _hashed_location(f"vauxhall-{agent}", identity)
        now = time.time()
        # The directory holds only start files, claimed or not, and their
        # temporary copies.
        remove_old_files(directory, "*", _TOOL_START_MAX_AGE_SECONDS, now)
        write_atomically(
            directory / f"{unique_name(prefix)}.time",
            str(now),
            private=True,
            durable=False,
        )


def claim_tool_duration(agent: str, identity: object) -> float | None:
    """Claim the most recent start recorded for a tool call and return its age.

    A start is claimed by renaming its file before reading it, so concurrent
    finishing hooks never share one. Claiming the most recent start keeps a
    start left by a call that never finished from inflating a later call's
    duration. Identical overlapping calls cannot be told apart, so they may
    report each other's durations.

    Args:
        agent: The agent whose timing directory is used.
        identity: Value identifying the tool call.

    Returns:
        The call's duration in seconds, or ``None`` when no start can be claimed.
    """
    try:
        directory, prefix = _hashed_location(f"vauxhall-{agent}", identity)
        starts = sorted(directory.glob(f"{prefix}*.time"), reverse=True)
    except OSError:
        return None
    for path in starts:
        try:
            claimed = claim(path)
        except OSError:
            continue  # Another finishing hook claimed this start first.
        try:
            started_at = float(claimed.read_text())
        except (OSError, ValueError):
            continue
        finally:
            claimed.unlink(missing_ok=True)
        return round(time.time() - started_at, 1)
    return None


def claim_tool_use_duration(agent: str, input_data: dict[str, Any]) -> float | None:
    """Claim the start recorded for the event's tool call and return its age.

    Args:
        agent: The agent whose timing directory is used.
        input_data: The hook event identifying the tool call by tool-use ID.

    Returns:
        The call's duration in seconds, or ``None`` when the event has no
        tool-use ID or no start can be claimed.
    """
    identity = tool_use_identity(input_data)
    return claim_tool_duration(agent, identity) if identity else None
