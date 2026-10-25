# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the local record of each session's tmux pane."""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path

import pytest

from tests.hooks.interleaving import after_first_write_open
from vauxhall.hooks import panes

TMUX_ENV = {"TMUX_PANE": "%3", "TMUX": "/run/tmux-1000/default,4242,0"}


def test_record_pane_stores_pane_socket_and_server() -> None:
    """A session started in tmux gets a record naming its pane and server."""
    panes.record_pane("Codex", "native:1", TMUX_ENV)

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242
    )


def test_record_pane_stores_the_foreground_process_group() -> None:
    """The agent's process group is kept, to tell it from what follows it."""
    panes.record_pane("codex", "native:1", TMUX_ENV, process_group=500)

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242, 500
    )


class FakeRun:
    """Answers tmux and ``ps`` like a pane running an agent, and records them."""

    def __init__(self, ps_output: bytes = b"    500\n", fail_on: str = "") -> None:
        """Create the fake.

        Args:
            ps_output: What ``ps`` prints.
            fail_on: ``tmux`` or ``ps`` to make that command fail.
        """
        self.commands: list[list[str]] = []
        self.ps_output = ps_output
        self.fail_on = fail_on

    def __call__(
        self, command: list[str], **options: object
    ) -> "subprocess.CompletedProcess[bytes]":
        """Run a fake command.

        Args:
            command: The command line.
            **options: The ``subprocess.run`` options.

        Returns:
            A completed process.

        Raises:
            subprocess.CalledProcessError: For the command set to fail.
        """
        assert options["timeout"] == panes.TMUX_TIMEOUT_SECONDS
        self.commands.append(command)
        if command[0] == self.fail_on:
            raise subprocess.CalledProcessError(1, command)
        stdout = b"4242 100\n" if command[0] == "tmux" else self.ps_output
        return subprocess.CompletedProcess(command, 0, stdout, b"")


def test_foreground_process_group_asks_the_session_tmux_server() -> None:
    """The pane's first process comes from tmux, and its terminal from ``ps``."""
    run = FakeRun()

    assert panes.foreground_process_group(TMUX_ENV, run) == 500
    assert run.commands == [
        [
            "tmux",
            "-S",
            "/run/tmux-1000/default",
            "display-message",
            "-p",
            "-t",
            "%3",
            "#{pid} #{pane_pid}",
        ],
        ["ps", "-o", "tpgid=", "-p", "100"],
    ]


@pytest.mark.parametrize(
    "environment", [{}, {"TMUX_PANE": "%3"}, {"TMUX_PANE": "x", "TMUX": "/s,1,0"}]
)
def test_foreground_process_group_is_unknown_outside_tmux(
    environment: dict[str, str],
) -> None:
    """Without a pane and its server there is nothing to ask.

    Args:
        environment: An environment without a usable pane or server.
    """
    run = FakeRun()

    assert panes.foreground_process_group(environment, run) is None
    assert run.commands == []


@pytest.mark.parametrize(
    ("ps_output", "fail_on"),
    [(b"   -1\n", ""), (b"", ""), (b"    500\n", "ps"), (b"    500\n", "tmux")],
)
def test_foreground_process_group_is_unknown_when_it_cannot_be_read(
    ps_output: bytes, fail_on: str
) -> None:
    """No terminal, no answer, or a failing command leave the group unknown.

    Args:
        ps_output: What ``ps`` prints.
        fail_on: The command that fails, if any.
    """
    run = FakeRun(ps_output, fail_on)

    assert panes.foreground_process_group(TMUX_ENV, run) is None


@pytest.mark.skipif(
    shutil.which("tmux") is None or shutil.which("ps") is None,
    reason="needs tmux and ps",
)
def test_pane_process_group_reads_a_real_pane() -> None:
    """Real tmux and ``ps`` output parse to the server and the pane's group."""
    # A socket path is limited to about 100 bytes, too few for tmp_path.
    directory = Path(tempfile.mkdtemp(prefix="vauxhall-", dir="/tmp"))
    socket = str(directory / "s")
    try:
        panes.run_tmux(socket, "-f", "/dev/null", "new-session", "-d", "exec sleep 30")
        details = panes.run_tmux(
            socket, "display-message", "-p", "-t", "%0", "#{pid} #{pane_pid}"
        )
        server_pid, pane_pid = details.stdout.decode().split()
        # The pane's process takes its terminal just after tmux starts it.
        deadline = time.monotonic() + 2
        while (result := panes.pane_process_group(socket, "%0"))[1] is None:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    finally:
        with suppress(subprocess.CalledProcessError):
            panes.run_tmux(socket, "kill-server")
        shutil.rmtree(directory)

    assert result == (server_pid, int(pane_pid))


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")
def test_an_existing_reachable_directory_is_made_private() -> None:
    """A directory made before the hooks, with a looser mode, is tightened."""
    directory = Path.home() / ".config" / "vauxhall" / "panes"
    directory.mkdir(parents=True)
    directory.chmod(0o755)

    panes.record_pane("codex", "native:1", TMUX_ENV)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")
def test_records_are_private() -> None:
    """Only the owner can read the directory and its records."""
    panes.record_pane("codex", "native:1", TMUX_ENV)

    directory = panes.panes_directory()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    (record,) = directory.glob("*.json")
    assert stat.S_IMODE(record.stat().st_mode) == 0o600


@pytest.mark.parametrize("environment", [{}, {"TMUX_PANE": "-t evil"}])
def test_record_pane_removes_record_without_a_usable_pane(
    environment: dict[str, str],
) -> None:
    """A session outside tmux, or with an unrecognized pane id, is not reachable.

    Args:
        environment: An environment without a valid ``TMUX_PANE``.
    """
    panes.record_pane("codex", "native:1", TMUX_ENV)

    panes.record_pane("codex", "native:1", environment)

    assert panes.load_pane("codex", "native:1") is None


@pytest.mark.parametrize(
    ("tmux", "socket", "server_pid"),
    [("", None, None), ("sock,x,0", "sock", None)],
)
def test_record_pane_tolerates_an_unusable_tmux_variable(
    tmux: str, socket: str | None, server_pid: int | None
) -> None:
    """A missing or malformed ``TMUX`` leaves the unknown parts unset.

    Args:
        tmux: The ``TMUX`` value.
        socket: The socket expected to be recorded.
        server_pid: The server PID expected to be recorded.
    """
    panes.record_pane("codex", "native:1", {"TMUX_PANE": "%7", "TMUX": tmux})

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%7", socket, server_pid
    )


def test_sessions_and_agents_have_separate_records() -> None:
    """Records are keyed by agent and session together."""
    panes.record_pane("codex", "native:1", TMUX_ENV)
    panes.record_pane("claude", "native:1", {"TMUX_PANE": "%9"})

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242
    )
    assert panes.load_pane("claude", "native:1") == panes.PaneTarget("%9", None, None)
    assert panes.load_pane("codex", "native:2") is None


def test_forget_pane_removes_the_record() -> None:
    """A session that ended stops being reachable, and forgetting twice is fine."""
    panes.record_pane("codex", "native:1", TMUX_ENV)

    panes.forget_pane("codex", "native:1")
    panes.forget_pane("codex", "native:1")

    assert panes.load_pane("codex", "native:1") is None


def test_record_pane_sweeps_records_of_long_ended_sessions() -> None:
    """A record nobody refreshed for a month is removed when another is written."""
    panes.record_pane("codex", "old", TMUX_ENV)
    (old,) = panes.panes_directory().glob("*.json")
    month_ago = time.time() - 31 * 24 * 60 * 60
    os.utime(old, (month_ago, month_ago))

    panes.record_pane("codex", "new", TMUX_ENV)

    assert panes.load_pane("codex", "old") is None
    assert panes.load_pane("codex", "new") is not None


@pytest.mark.parametrize("content", ["[]", json.dumps({"pane": "3"})])
def test_load_pane_rejects_invalid_records(content: str) -> None:
    """A tampered record that isn't an object or names no pane is treated as missing.

    Args:
        content: The text of an invalid record.
    """
    panes.record_pane("codex", "native:1", TMUX_ENV)
    (record,) = panes.panes_directory().glob("*.json")
    record.write_text(content, encoding="utf-8")

    assert panes.load_pane("codex", "native:1") is None


def test_load_pane_drops_malformed_optional_fields() -> None:
    """A wrong-typed socket or server PID is ignored while the pane is kept."""
    panes.record_pane("codex", "native:1", TMUX_ENV)
    (record,) = panes.panes_directory().glob("*.json")
    record.write_text(
        json.dumps(
            {"pane": "%3", "socket": 5, "server_pid": True, "process_group": "7"}
        ),
        encoding="utf-8",
    )

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget("%3", None, None)


def test_session_with_a_lone_surrogate_gets_a_record() -> None:
    """JSON hook input can carry a lone surrogate, which UTF-8 rejects."""
    panes.record_pane("codex", "native:\ud800abc", TMUX_ENV)

    assert panes.load_pane("codex", "native:\ud800abc") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242
    )


def test_concurrent_records_of_one_session_do_not_clobber_each_other() -> None:
    """A second writer for the session leaves the first one's write intact."""
    with after_first_write_open(
        lambda: panes.record_pane("codex", "native:1", {"TMUX_PANE": "%9"})
    ):
        panes.record_pane("codex", "native:1", TMUX_ENV)

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242
    )
    assert [path.suffix for path in panes.panes_directory().iterdir()] == [".json"]
