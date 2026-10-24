# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the local record of each session's tmux pane."""

import json
import os
import stat
import subprocess
import time

import pytest

from vauxhall.hooks import panes

TMUX_ENV = {"TMUX_PANE": "%3", "TMUX": "/run/tmux-1000/default,4242,0"}


def test_record_pane_stores_pane_socket_and_server() -> None:
    """A session started in tmux gets a record naming its pane and server."""
    panes.record_pane("Codex", "native:1", TMUX_ENV)

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242
    )


def test_record_pane_stores_the_foreground_command() -> None:
    """The agent's command is kept, to tell it from a shell left behind."""
    panes.record_pane("codex", "native:1", TMUX_ENV, command="node")

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242, "node"
    )


def test_foreground_command_asks_the_session_tmux_server() -> None:
    """The query names the pane and the server the hook runs under."""
    commands: list[list[str]] = []

    def tmux(
        command: list[str], **_options: object
    ) -> "subprocess.CompletedProcess[bytes]":
        """Answer like tmux for a pane running Claude Code.

        Args:
            command: The command line.
            **_options: The ``subprocess.run`` options.

        Returns:
            A completed process.
        """
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, b"claude\n", b"")

    assert panes.foreground_command(TMUX_ENV, tmux) == "claude"
    assert commands == [
        [
            "tmux",
            "-S",
            "/run/tmux-1000/default",
            "display-message",
            "-p",
            "-t",
            "%3",
            "#{pane_current_command}",
        ]
    ]


@pytest.mark.parametrize(
    "environment", [{}, {"TMUX_PANE": "%3"}, {"TMUX_PANE": "x", "TMUX": "/s,1,0"}]
)
def test_foreground_command_is_unknown_outside_tmux(
    environment: dict[str, str],
) -> None:
    """Without a pane and its server there is nothing to ask.

    Args:
        environment: An environment without a usable pane or server.
    """

    def tmux(_command: list[str], **_options: object) -> None:
        """Fail the test if tmux is run.

        Args:
            _command: The command line.
            **_options: The ``subprocess.run`` options.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError

    assert panes.foreground_command(environment, tmux) is None


def test_foreground_command_is_unknown_when_tmux_fails() -> None:
    """A tmux error leaves the command unknown instead of failing the hook."""

    def tmux(command: list[str], **_options: object) -> None:
        """Fail like a tmux server that went away.

        Args:
            command: The command line.
            **_options: The ``subprocess.run`` options.

        Raises:
            subprocess.CalledProcessError: Always.
        """
        raise subprocess.CalledProcessError(1, command)

    assert panes.foreground_command(TMUX_ENV, tmux) is None


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
        json.dumps({"pane": "%3", "socket": 5, "server_pid": True, "command": 7}),
        encoding="utf-8",
    )

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget("%3", None, None)
