# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the runtime helpers shared by the built-in hooks."""

from pathlib import Path
from unittest.mock import patch

from vauxhall.hooks import common

IDENTITY = ["session-123", "call-123"]


def test_claim_skips_start_claimed_by_another_hook(tmp_path: Path) -> None:
    """A start renamed away by a concurrent hook must not be claimed twice."""
    real_rename = Path.rename
    lost_races: list[Path] = []

    def rename_after_losing_first_race(path: Path, target: Path) -> Path:
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
    """A start file that cannot be parsed is removed and the next one is used."""
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
