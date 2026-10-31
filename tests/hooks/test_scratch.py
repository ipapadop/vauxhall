# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the hooks' scratch files."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.hooks.interleaving import after_first_write_open
from vauxhall.hooks import scratch

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
        patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(scratch.time, "time", side_effect=[1000.0, 1004.0, 1010.0]),
    ):
        scratch.record_tool_start("test", IDENTITY)
        scratch.record_tool_start("test", IDENTITY)
        with patch.object(Path, "rename", rename_after_losing_first_race):
            duration = scratch.claim_tool_duration("test", IDENTITY)

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
        patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(scratch.time, "time", side_effect=[1000.0, 1004.0, 1010.0]),
    ):
        scratch.record_tool_start("test", IDENTITY)
        scratch.record_tool_start("test", IDENTITY)
        newest = max(tmp_path.rglob("*.time"))
        newest.write_text("not a time")
        duration = scratch.claim_tool_duration("test", IDENTITY)

    assert duration == 10.0
    assert not list(tmp_path.rglob("*.time"))
    assert not list(tmp_path.rglob("*.claimed"))


def test_record_tool_start_sweeps_starts_older_than_a_day(tmp_path: Path) -> None:
    """Starts of calls that never finished don't pile up.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        directory = scratch.private_directory("vauxhall-test")
        old = time.time() - scratch._TOOL_START_MAX_AGE_SECONDS - 60
        stale = [directory / name for name in ("a.time", "b.tmp", "c.x.claimed")]
        for path in stale:
            path.write_text("0")
            os.utime(path, (old, old))
        recent = directory / "d.time"
        recent.write_text("0")

        scratch.record_tool_start("test", IDENTITY)

    assert not any(path.exists() for path in stale)
    assert recent.exists()
    assert len(list(directory.glob("*.time"))) == 2


@pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="Windows ignores creation modes, and its temporary directory is per account",
)
def test_record_tool_start_creates_an_owner_only_directory(tmp_path: Path) -> None:
    """Tool start times are kept where no other account can list or read them.

    Args:
        tmp_path: Pytest temporary directory.
    """
    previous_umask = os.umask(0o022)
    try:
        with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
            scratch.record_tool_start("test", IDENTITY)
    finally:
        os.umask(previous_umask)

    directory = tmp_path / f"vauxhall-test{scratch._USER_SUFFIX}"
    assert directory.stat().st_mode & 0o777 == 0o700
    assert len(list(directory.glob("*.time"))) == 1


@pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="Windows has no mode bits to plant, and its temporary directory is "
    "per account",
)
def test_tool_timing_repairs_a_directory_others_could_reach(tmp_path: Path) -> None:
    """Durations keep working in a timing directory left reachable.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        scratch.record_tool_start("test", IDENTITY)
        [start] = tmp_path.rglob("*.time")
        start.parent.chmod(0o775)

        scratch.record_tool_start("test", IDENTITY)
        duration = scratch.claim_tool_duration("test", IDENTITY)

    assert duration is not None
    assert start.parent.stat().st_mode & 0o777 == 0o700


def test_record_tool_start_writes_nothing_through_a_planted_symlink(
    tmp_path: Path,
) -> None:
    """Tool start times never reach a directory another account redirected.

    Args:
        tmp_path: Pytest temporary directory.
    """
    elsewhere = tmp_path / "attacker"
    elsewhere.mkdir()
    (tmp_path / f"vauxhall-test{scratch._USER_SUFFIX}").symlink_to(elsewhere)

    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        scratch.record_tool_start("test", IDENTITY)
        duration = scratch.claim_tool_duration("test", IDENTITY)

    assert duration is None
    assert not list(elsewhere.iterdir())


def test_private_directory_allows_a_platform_without_posix_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A platform that reports no owner and no mode bits must still be usable.

    Windows ignores the mode a directory is created with, reports every
    directory as world accessible, and has no ``os.getuid``.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setattr(scratch.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.delattr(scratch.os, "getuid", raising=False)
    directory = tmp_path / f"vauxhall-messages-claude{scratch._USER_SUFFIX}"
    directory.mkdir()
    directory.chmod(0o777)

    assert scratch.private_directory("vauxhall-messages-claude") == directory


def test_collect_message_chunks_returns_one_bounded_message(tmp_path: Path) -> None:
    """Streaming text is kept private and published once per completed message.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        assert (
            scratch.collect_message_chunk(
                "claude", ["session", "message"], "Hello ", final=False
            )
            is None
        )
        assert (
            scratch.collect_message_chunk(
                "claude", ["session", "other"], "Other", final=True
            )
            == "Other"
        )
        assert (
            scratch.collect_message_chunk(
                "claude", ["session", "message"], "world", final=True
            )
            == "Hello world"
        )

    assert not list(tmp_path.rglob("*.chunk"))


def test_collect_message_chunks_keeps_a_lone_surrogate(tmp_path: Path) -> None:
    """JSON hook input can carry a lone surrogate, which UTF-8 rejects.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        scratch.collect_message_chunk("claude", ["session"], "a\ud800", final=False)
        message = scratch.collect_message_chunk("claude", ["session"], "b", final=True)

    assert message == "a\ud800b"


def test_collect_message_chunks_caps_long_text(tmp_path: Path) -> None:
    """A long reply fits the telemetry detail string limit.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        message = scratch.collect_message_chunk(
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
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        scratch.collect_message_chunk("gemini", ["session"], "old", final=False)
        scratch.discard_message_chunks("gemini", ["session"])
        message = scratch.collect_message_chunk(
            "gemini", ["session"], "new", final=True
        )

    assert message == "new"


def test_collect_message_chunk_sweeps_text_of_long_abandoned_responses(
    tmp_path: Path,
) -> None:
    """Text of a response unfinished for over a day is removed on the next chunk.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        scratch.collect_message_chunk("codex", ["old"], "old", final=False)
        scratch.collect_message_chunk("codex", ["recent"], "recent", final=False)
        old, recent = sorted(
            tmp_path.rglob("*.chunk"), key=lambda path: path.read_text()
        )
        day_ago = time.time() - 25 * 60 * 60
        os.utime(old, (day_ago, day_ago))

        scratch.collect_message_chunk("codex", ["new"], "new", final=False)

    assert not old.exists()
    assert recent.exists()


@pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="Windows has no mode bits to plant, and its temporary directory is "
    "per account",
)
def test_private_directory_makes_an_owned_reachable_directory_private(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An owned directory others could reach is repaired, not refused.

    Args:
        tmp_path: Pytest temporary directory.
        caplog: Pytest log capture fixture.
    """
    loose = tmp_path / f"vauxhall-claude{scratch._USER_SUFFIX}"
    loose.mkdir()
    loose.chmod(0o775)
    kept = loose / "start.time"
    kept.write_text("1")

    with (
        patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)),
        caplog.at_level("WARNING"),
    ):
        directory = scratch.private_directory("vauxhall-claude")

    assert directory == loose
    assert loose.stat().st_mode & 0o777 == 0o700
    assert kept.exists()
    assert "Made" in caplog.text


@pytest.mark.skipif(
    not hasattr(os, "getuid"), reason="Windows names no owner and ignores modes"
)
def test_make_private_removes_entries_another_account_owns(tmp_path: Path) -> None:
    """Entries planted while the directory was reachable are removed.

    Args:
        tmp_path: Pytest temporary directory.
    """
    loose = tmp_path / "loose"
    loose.mkdir()
    loose.chmod(0o777)
    (loose / "mine").write_text("1")
    (loose / "planted").symlink_to(tmp_path / "elsewhere")
    real_scandir = os.scandir

    class Foreign:
        """A directory entry owned by another account."""

        def __init__(self, entry: os.DirEntry[str]) -> None:
            self.path = entry.path
            self._entry = entry

        def stat(self, *, follow_symlinks: bool) -> os.stat_result:
            info = self._entry.stat(follow_symlinks=follow_symlinks)
            if self._entry.name != "planted":
                return info
            return os.stat_result((info.st_mode, 0, 0, 0, os.getuid() + 1, *info[5:]))

    with patch.object(
        scratch.os, "scandir", lambda path: [Foreign(e) for e in real_scandir(path)]
    ):
        scratch._make_private(loose)

    assert sorted(path.name for path in loose.iterdir()) == ["mine"]


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

    with patch.object(scratch.tempfile, "gettempdir", return_value=str(tmp_path)):
        message = scratch.collect_message_chunk("claude", ["s"], "secret", final=True)

    assert message is None
    assert not list(elsewhere.iterdir())


def test_concurrent_chunks_of_one_message_are_all_kept(
    isolated_tempdir: Path,
) -> None:
    """A chunk stored while another is being stored does not replace it.

    Args:
        isolated_tempdir: The directory standing in for the system one.
    """
    with after_first_write_open(
        lambda: scratch.collect_message_chunk("claude", ["s"], "second ", final=False)
    ):
        scratch.collect_message_chunk("claude", ["s"], "first ", final=False)
    message = scratch.collect_message_chunk("claude", ["s"], "end", final=True)

    assert message in {"first second end", "second first end"}
    assert not [path for path in isolated_tempdir.rglob("*") if path.is_file()]


def test_concurrent_final_chunks_never_share_text() -> None:
    """Two hooks ending one message publish each stored chunk only once."""
    scratch.collect_message_chunk("claude", ["s"], "stored ", final=False)
    claim = scratch.claim
    pending = [lambda: scratch.collect_message_chunk("claude", ["s"], "a", final=True)]
    other: list[str | None] = []

    def claim_after_other_final(path: Path) -> Path:
        # Another hook ends the message just before this one claims a chunk.
        while pending:
            other.append(pending.pop()())
        return claim(path)

    with patch.object(scratch, "claim", claim_after_other_final):
        message = scratch.collect_message_chunk("claude", ["s"], "b", final=True)

    assert sorted([message, *other]) == ["b", "stored a"]


def test_claim_renames_the_file_and_marks_it_fresh(tmp_path: Path) -> None:
    """A claimed file is not mistaken for an old leftover by an age sweep.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "cursor"
    path.write_text("0", encoding="ascii")
    day_ago = time.time() - 25 * 60 * 60
    os.utime(path, (day_ago, day_ago))

    claimed = scratch.claim(path)

    assert not path.exists()
    assert claimed.read_text(encoding="ascii") == "0"
    assert claimed.stat().st_mtime > day_ago + 60


def test_claim_fails_for_a_file_already_claimed(tmp_path: Path) -> None:
    """Only one process can claim a file.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "cursor"
    path.write_text("0", encoding="ascii")
    scratch.claim(path)

    with pytest.raises(FileNotFoundError):
        scratch.claim(path)
