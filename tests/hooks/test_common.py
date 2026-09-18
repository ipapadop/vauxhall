# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the runtime helpers shared by the built-in hooks."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.hooks import common

IDENTITY = ["session-123", "call-123"]


def test_claim_skips_start_claimed_by_another_hook(tmp_path: Path) -> None:
    """A start renamed away by a concurrent hook must not be claimed twice.

    Args:
        tmp_path: Pytest temporary directory.
    """
    real_rename = Path.rename
    lost_races: list[Path] = []

    def rename_after_losing_first_race(path: Path, target: Path) -> Path:
        """Fail the first rename as a competing hook would, then behave normally.

        Args:
            path: The start file being claimed.
            target: Name the claimed file is given.

        Returns:
            The renamed path.

        Raises:
            FileNotFoundError: On the first call, as a lost race would.
        """
        if not lost_races:
            lost_races.append(path)
            path.unlink()
            raise FileNotFoundError(path)
        return real_rename(path, target)

    with (
        patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(common.time, "time", side_effect=[1000.0, 1004.0, 1010.0]),
    ):
        common.record_tool_start("test", IDENTITY)
        common.record_tool_start("test", IDENTITY)
        with patch.object(Path, "rename", rename_after_losing_first_race):
            duration = common.claim_tool_duration("test", IDENTITY)

    assert duration == 10.0
    assert len(lost_races) == 1
    assert not list(tmp_path.rglob("*.time"))
    assert not list(tmp_path.rglob("*.claimed"))


def test_claim_discards_unreadable_start(tmp_path: Path) -> None:
    """A start file that cannot be parsed is removed and the next one is used.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with (
        patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(common.time, "time", side_effect=[1000.0, 1004.0, 1010.0]),
    ):
        common.record_tool_start("test", IDENTITY)
        common.record_tool_start("test", IDENTITY)
        newest = max(tmp_path.rglob("*.time"))
        newest.write_text("not a time")
        duration = common.claim_tool_duration("test", IDENTITY)

    assert duration == 10.0
    assert not list(tmp_path.rglob("*.time"))
    assert not list(tmp_path.rglob("*.claimed"))


def test_collect_message_chunks_returns_one_bounded_message(tmp_path: Path) -> None:
    """Streaming text is kept private and published once per completed message.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        assert (
            common.collect_message_chunk(
                "claude", ["session", "message"], "Hello ", final=False
            )
            is None
        )
        assert (
            common.collect_message_chunk(
                "claude", ["session", "other"], "Other", final=True
            )
            == "Other"
        )
        assert (
            common.collect_message_chunk(
                "claude", ["session", "message"], "world", final=True
            )
            == "Hello world"
        )

    assert not list(tmp_path.rglob("*.message"))


def test_collect_message_chunks_caps_long_text(tmp_path: Path) -> None:
    """A long reply fits the telemetry detail string limit.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        message = common.collect_message_chunk(
            "gemini", ["session"], "x" * 5000, final=True
        )

    assert message == "x" * 4095 + "…"


def test_discard_message_chunks_prevents_next_turn_contamination(
    tmp_path: Path,
) -> None:
    """An unfinished response is cleared before a new turn begins.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        common.collect_message_chunk("gemini", ["session"], "old", final=False)
        common.discard_message_chunks("gemini", ["session"])
        message = common.collect_message_chunk("gemini", ["session"], "new", final=True)

    assert message == "new"


def test_private_directory_rejects_a_directory_another_account_could_reach(
    tmp_path: Path,
) -> None:
    """A pre-created world-writable directory is refused, not reused.

    Args:
        tmp_path: Pytest temporary directory.
    """
    suffix = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
    planted = tmp_path / f"vauxhall-messages-claude{suffix}"
    planted.mkdir()
    planted.chmod(0o777)

    with (
        patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)),
        pytest.raises(OSError, match="not a private directory"),
    ):
        common.private_directory("vauxhall-messages-claude")


def test_collect_message_chunk_writes_nothing_through_a_planted_symlink(
    tmp_path: Path,
) -> None:
    """Assistant text never reaches a directory another account redirected.

    Args:
        tmp_path: Pytest temporary directory.
    """
    suffix = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
    elsewhere = tmp_path / "attacker"
    elsewhere.mkdir()
    (tmp_path / f"vauxhall-messages-claude{suffix}").symlink_to(elsewhere)

    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        message = common.collect_message_chunk("claude", ["s"], "secret", final=True)

    assert message is None
    assert not list(elsewhere.iterdir())
