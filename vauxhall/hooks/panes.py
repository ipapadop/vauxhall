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
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from vauxhall.hooks.files import remove_old_files, write_atomically

_PANE_PATTERN = re.compile(r"%\d+")
_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
TMUX_TIMEOUT_SECONDS = 1


@dataclass(frozen=True)
class PaneTarget:
    """A tmux pane an agent session was started in.

    Attributes:
        pane: The pane identifier, such as ``%3``.
        socket: Path of the tmux server's socket, or ``None`` for the default.
        server_pid: Process ID of the tmux server the pane belonged to, used to
            tell that pane from an unrelated one after the server restarts.
        command: The pane's foreground command when the session started, such
            as ``claude`` or ``node``, used to tell the agent from the shell
            left behind when it exits without ending its session; ``None``
            when unknown.
    """

    pane: str
    socket: str | None
    server_pid: int | None
    command: str | None = None


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
    # Hook input is JSON, which can carry a lone surrogate.
    identity = f"{agent.lower()}\0{session_id}".encode(errors="surrogatepass")
    key = hashlib.sha256(identity).hexdigest()
    return panes_directory() / f"{key}.json"


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


def foreground_command(
    environment: Mapping[str, str] | None = None,
    run: Callable[..., "subprocess.CompletedProcess[bytes]"] = subprocess.run,
) -> str | None:
    """Return the name of the command running in the foreground of this pane.

    Args:
        environment: Environment to read ``TMUX_PANE`` and ``TMUX`` from,
            defaulting to the process environment.
        run: Function that runs tmux, ``subprocess.run`` by default.

    Returns:
        The command name, or ``None`` outside tmux or when tmux can't say.
    """
    source = os.environ if environment is None else environment
    pane = source.get("TMUX_PANE", "")
    socket, _ = _server_details(source.get("TMUX", ""))
    if not _PANE_PATTERN.fullmatch(pane) or socket is None:
        return None
    try:
        result = run(
            [
                "tmux",
                "-S",
                socket,
                "display-message",
                "-p",
                "-t",
                pane,
                "#{pane_current_command}",
            ],
            capture_output=True,
            timeout=TMUX_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.decode(errors="replace").strip() or None


def record_pane(
    agent: str,
    session_id: str,
    environment: Mapping[str, str] | None = None,
    command: str | None = None,
) -> None:
    """Remember the tmux pane a session started in, or forget a stale one.

    A session that is not in tmux has any earlier record removed, so a resumed
    session outside tmux never receives prompts meant for its old pane.

    Args:
        agent: The agent name.
        session_id: The session identity.
        environment: Environment to read ``TMUX_PANE`` and ``TMUX`` from,
            defaulting to the process environment.
        command: The pane's foreground command, from ``foreground_command``.

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
    write_atomically(
        path,
        json.dumps(
            {
                "pane": pane,
                "socket": socket,
                "server_pid": server_pid,
                "command": command,
            }
        ),
    )
    # Also sweeps temporary files left by a writer that died.
    remove_old_files(path.parent, "*", _MAX_AGE_SECONDS)


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
    pane, socket, server_pid, command = (
        data.get("pane"),
        data.get("socket"),
        data.get("server_pid"),
        data.get("command"),
    )
    if not isinstance(pane, str) or not _PANE_PATTERN.fullmatch(pane):
        return None
    if not isinstance(socket, str) or not socket:
        socket = None
    if isinstance(server_pid, bool) or not isinstance(server_pid, int):
        server_pid = None
    if not isinstance(command, str) or not command:
        command = None
    return PaneTarget(pane, socket, server_pid, command)
