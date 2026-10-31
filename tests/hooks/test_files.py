# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the hooks' file helpers."""

import os
import time
from pathlib import Path

import pytest

from vauxhall.hooks.files import claim


def test_claim_renames_the_file_and_marks_it_fresh(tmp_path: Path) -> None:
    """A claimed file is not mistaken for an old leftover by an age sweep.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "cursor"
    path.write_text("0", encoding="ascii")
    day_ago = time.time() - 25 * 60 * 60
    os.utime(path, (day_ago, day_ago))

    claimed = claim(path)

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
    claim(path)

    with pytest.raises(FileNotFoundError):
        claim(path)
