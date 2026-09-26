# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the local record of each session's tmux pane."""

import json
import os
import stat
import time
from pathlib import Path

import pytest

from vauxhall.hooks import panes

TMUX_ENV = {"TMUX_PANE": "%3", "TMUX": "/run/tmux-1000/default,4242,0"}


def test_record_pane_stores_pane_socket_and_server() -> None:
    """A session started in tmux gets a record naming its pane and server."""
    panes.record_pane("Codex", "native:1", TMUX_ENV)

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget(
        "%3", "/run/tmux-1000/default", 4242
    )


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")
def test_records_are_private() -> None:
    """Only the owner can read the directory and its records."""
    panes.record_pane("codex", "native:1", TMUX_ENV)

    directory = panes.panes_directory()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    (record,) = directory.glob("*.json")
    assert stat.S_IMODE(record.stat().st_mode) == 0o600


def test_record_pane_removes_record_when_not_in_tmux() -> None:
    """A session that moved outside tmux no longer receives prompts."""
    panes.record_pane("codex", "native:1", TMUX_ENV)

    panes.record_pane("codex", "native:1", {})

    assert panes.load_pane("codex", "native:1") is None


def test_record_pane_ignores_unrecognized_pane_ids() -> None:
    """An environment value that is not a pane id is never stored."""
    panes.record_pane("codex", "native:1", {"TMUX_PANE": "-t evil"})

    assert panes.load_pane("codex", "native:1") is None


def test_record_pane_without_tmux_variable_has_no_server() -> None:
    """A pane without ``TMUX`` uses tmux's default socket and skips the server check."""
    panes.record_pane("codex", "native:1", {"TMUX_PANE": "%7"})

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget("%7", None, None)


def test_record_pane_tolerates_a_non_numeric_server() -> None:
    """A malformed ``TMUX`` value leaves the server unknown."""
    panes.record_pane("codex", "native:1", {"TMUX_PANE": "%7", "TMUX": "sock,x,0"})

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget("%7", "sock", None)


def test_sessions_and_agents_have_separate_records() -> None:
    """Records are keyed by agent and session together."""
    panes.record_pane("codex", "native:1", TMUX_ENV)
    panes.record_pane("claude", "native:1", {"TMUX_PANE": "%9"})

    assert panes.load_pane("codex", "native:1").pane == "%3"  # type: ignore[union-attr]
    assert panes.load_pane("claude", "native:1").pane == "%9"  # type: ignore[union-attr]
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


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"pane": "3"}),
        json.dumps({"pane": 3}),
    ],
)
def test_load_pane_rejects_invalid_records(content: str) -> None:
    """A damaged or tampered record is treated as missing.

    Args:
        content: The text of an invalid record.
    """
    panes.record_pane("codex", "native:1", TMUX_ENV)
    (record,) = panes.panes_directory().glob("*.json")
    Path(record).write_text(content, encoding="utf-8")

    assert panes.load_pane("codex", "native:1") is None


def test_load_pane_drops_malformed_optional_fields() -> None:
    """A wrong-typed socket or server PID is ignored while the pane is kept."""
    panes.record_pane("codex", "native:1", TMUX_ENV)
    (record,) = panes.panes_directory().glob("*.json")
    record.write_text(
        json.dumps({"pane": "%3", "socket": 5, "server_pid": True}), encoding="utf-8"
    )

    assert panes.load_pane("codex", "native:1") == panes.PaneTarget("%3", None, None)
