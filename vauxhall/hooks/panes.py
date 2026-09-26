# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Local record of which tmux pane each agent session runs in.

The hooks write it, and ``vauxhall-relay`` reads it to type dashboard prompts
into the right pane. It stays on the agent machine; nothing here is published.
"""

import hashlib
import json
import os
import re
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_PANE_PATTERN = re.compile(r"%\d+")
_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class PaneTarget:
    """A tmux pane an agent session was started in.

    Attributes:
        pane: The pane identifier, such as ``%3``.
        socket: Path of the tmux server's socket, or ``None`` for the default.
        server_pid: Process ID of the tmux server the pane belonged to, used to
            tell that pane from an unrelated one after the server restarts.
    """

    pane: str
    socket: str | None
    server_pid: int | None


def panes_directory() -> Path:
    """Return the private directory holding the records, creating it.

    Returns:
        The directory ``~/.config/vauxhall/panes``, readable only by this user.
    """
    directory = Path.home() / ".config" / "vauxhall" / "panes"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def _record_path(agent: str, session_id: str) -> Path:
    """Return the file holding one session's pane.

    Args:
        agent: The agent name.
        session_id: The session identity.

    Returns:
        A path named by a hash, since a session identity is not a safe file name.
    """
    key = hashlib.sha256(f"{agent.lower()}\0{session_id}".encode()).hexdigest()
    return panes_directory() / f"{key}.json"


def _sweep_old_records(directory: Path) -> None:
    """Remove records of sessions that have not started in a long time.

    Args:
        directory: The records directory.
    """
    cutoff = time.time() - _MAX_AGE_SECONDS
    with suppress(OSError):
        for record in directory.glob("*.json"):
            with suppress(OSError):
                if record.stat().st_mtime < cutoff:
                    record.unlink(missing_ok=True)


def _server_details(tmux: str) -> tuple[str | None, int | None]:
    """Split ``$TMUX`` into the server socket and process ID.

    Args:
        tmux: The ``TMUX`` value, ``<socket>,<server pid>,<session>``.

    Returns:
        The socket path and server PID, each ``None`` when not recognizable.
    """
    parts = tmux.rsplit(",", 2)
    if len(parts) != 3 or not parts[0]:
        return None, None
    return parts[0], int(parts[1]) if parts[1].isdecimal() else None


def record_pane(
    agent: str, session_id: str, environment: Mapping[str, str] | None = None
) -> None:
    """Remember the tmux pane a session started in, or forget a stale one.

    A session that is not in tmux has any earlier record removed, so a resumed
    session outside tmux never receives prompts meant for its old pane.

    Args:
        agent: The agent name.
        session_id: The session identity.
        environment: Environment to read ``TMUX_PANE`` and ``TMUX`` from,
            defaulting to the process environment.

    Raises:
        OSError: If the record cannot be written.
    """
    source = os.environ if environment is None else environment
    pane = source.get("TMUX_PANE", "")
    path = _record_path(agent, session_id)
    if not _PANE_PATTERN.fullmatch(pane):
        path.unlink(missing_ok=True)
        return
    socket, server_pid = _server_details(source.get("TMUX", ""))
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"pane": pane, "socket": socket, "server_pid": server_pid}, handle)
    temporary.replace(path)
    _sweep_old_records(path.parent)


def forget_pane(agent: str, session_id: str) -> None:
    """Remove the record of a session that ended.

    Args:
        agent: The agent name.
        session_id: The session identity.

    Raises:
        OSError: If the record cannot be removed.
    """
    _record_path(agent, session_id).unlink(missing_ok=True)


def load_pane(agent: str, session_id: str) -> PaneTarget | None:
    """Read the pane a session runs in.

    Args:
        agent: The agent name.
        session_id: The session identity.

    Returns:
        The pane, or ``None`` when there is no valid record for the session.
    """
    try:
        data = json.loads(_record_path(agent, session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pane, socket, server_pid = (
        data.get("pane"),
        data.get("socket"),
        data.get("server_pid"),
    )
    if not isinstance(pane, str) or not _PANE_PATTERN.fullmatch(pane):
        return None
    if not isinstance(socket, str) or not socket:
        socket = None
    if isinstance(server_pid, bool) or not isinstance(server_pid, int):
        server_pid = None
    return PaneTarget(pane, socket, server_pid)
