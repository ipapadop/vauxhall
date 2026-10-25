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
# Per command, for the hooks: SessionStart runs two, tmux and ps.
TMUX_TIMEOUT_SECONDS = 1.0

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


@dataclass(frozen=True)
class PaneTarget:
    """A tmux pane an agent session was started in.

    Attributes:
        pane: The pane identifier, such as ``%3``.
        socket: Path of the tmux server's socket, or ``None`` for the default.
        server_pid: Process ID of the tmux server the pane belonged to, used to
            tell that pane from an unrelated one after the server restarts.
        process_group: The pane terminal's foreground process group when the
            session started, the agent's own, used to tell the agent from
            the shell it leaves behind, or from another program started in
            the pane; ``None`` when unknown.
    """

    pane: str
    socket: str | None
    server_pid: int | None
    process_group: int | None = None


def panes_directory() -> Path:
    """Return the private directory holding the records, creating it.

    The creation mode doesn't apply to a directory that already exists, such as
    one made by hand or under a permissive umask, so its mode is tightened.

    Returns:
        The directory ``~/.config/vauxhall/panes``, readable only by this user.
    """
    directory = Path.home() / ".config" / "vauxhall" / "panes"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if hasattr(os, "getuid") and directory.stat().st_mode & 0o077:
        directory.chmod(0o700)
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


def run_tmux(
    socket: str | None,
    *arguments: str,
    data: bytes | None = None,
    run: Runner = subprocess.run,
    timeout: float = TMUX_TIMEOUT_SECONDS,
) -> "subprocess.CompletedProcess[bytes]":
    """Run one tmux command against a tmux server.

    Args:
        socket: The server's socket path, or ``None`` for the default server.
        *arguments: The tmux command and its arguments.
        data: Text for the command's standard input.
        run: Function that runs the command, ``subprocess.run`` by default.
        timeout: Seconds to wait for the command.

    Returns:
        The completed process.

    Raises:
        OSError: If tmux can't be run.
        subprocess.SubprocessError: If tmux fails or times out.
    """
    command = ["tmux", "-S", socket] if socket else ["tmux"]
    return run(
        [*command, *arguments],
        input=data,
        capture_output=True,
        timeout=timeout,
        check=True,
    )


def pane_process_group(
    socket: str | None,
    pane: str,
    run: Runner = subprocess.run,
    timeout: float = TMUX_TIMEOUT_SECONDS,
) -> tuple[str, int | None]:
    """Return a pane's tmux server PID and its terminal's foreground process group.

    tmux has no format for the process group, so ``ps`` reads it from the
    pane's first process. A program the pane runs leads its own group, so a
    restarted agent gets a new one even though its command name is the same.

    Args:
        socket: The tmux server's socket path, or ``None`` for the default.
        pane: The pane identifier.
        run: Function that runs tmux and ``ps``, ``subprocess.run`` by default.
        timeout: Seconds to wait for each command.

    Returns:
        The server PID as tmux prints it, and the process group, ``None`` when
        ``ps`` can't say.

    Raises:
        OSError: If tmux can't be run.
        subprocess.SubprocessError: If tmux doesn't know the pane.
    """
    result = run_tmux(
        socket,
        "display-message",
        "-p",
        "-t",
        pane,
        "#{pid} #{pane_pid}",
        run=run,
        timeout=timeout,
    )
    server_pid, _, pane_pid = (
        result.stdout.decode(errors="replace").strip().partition(" ")
    )
    if not pane_pid.isdecimal():
        return server_pid, None
    try:
        group = run(
            ["ps", "-o", "tpgid=", "-p", pane_pid],
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return server_pid, None
    # ps prints -1 for a process without a controlling terminal.
    value = group.stdout.decode(errors="replace").strip()
    return server_pid, int(value) if value.isdecimal() else None


def foreground_process_group(
    environment: Mapping[str, str] | None = None, run: Runner = subprocess.run
) -> int | None:
    """Return the foreground process group of the pane this process runs in.

    Args:
        environment: Environment to read ``TMUX_PANE`` and ``TMUX`` from,
            defaulting to the process environment.
        run: Function that runs tmux and ``ps``, ``subprocess.run`` by default.

    Returns:
        The process group, or ``None`` outside tmux or when it can't be read.
    """
    source = os.environ if environment is None else environment
    pane = source.get("TMUX_PANE", "")
    socket, _ = _server_details(source.get("TMUX", ""))
    if not _PANE_PATTERN.fullmatch(pane) or socket is None:
        return None
    try:
        return pane_process_group(socket, pane, run)[1]
    except (OSError, subprocess.SubprocessError):
        return None


def record_pane(
    agent: str,
    session_id: str,
    environment: Mapping[str, str] | None = None,
    process_group: int | None = None,
) -> None:
    """Remember the tmux pane a session started in, or forget a stale one.

    A session that is not in tmux has any earlier record removed, so a resumed
    session outside tmux never receives prompts meant for its old pane.

    Args:
        agent: The agent name.
        session_id: The session identity.
        environment: Environment to read ``TMUX_PANE`` and ``TMUX`` from,
            defaulting to the process environment.
        process_group: The pane's foreground process group, from
            ``foreground_process_group``.

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
                "process_group": process_group,
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
    pane, socket, server_pid, process_group = (
        data.get("pane"),
        data.get("socket"),
        data.get("server_pid"),
        data.get("process_group"),
    )
    if not isinstance(pane, str) or not _PANE_PATTERN.fullmatch(pane):
        return None
    if not isinstance(socket, str) or not socket:
        socket = None
    if isinstance(server_pid, bool) or not isinstance(server_pid, int):
        server_pid = None
    if (
        isinstance(process_group, bool)
        or not isinstance(process_group, int)
        or process_group <= 0
    ):
        process_group = None
    return PaneTarget(pane, socket, server_pid, process_group)
