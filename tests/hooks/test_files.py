# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the hooks' file helpers."""

import re
from pathlib import Path

import pytest

from vauxhall.hooks.files import write_atomically


def test_write_atomically_replaces_the_file(tmp_path: Path) -> None:
    """The new text replaces the old, and no temporary file is left.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "state"
    path.write_text("old", encoding="utf-8")

    write_atomically(path, "new")

    assert path.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.iterdir()) == [path]


def test_write_atomically_removes_its_temporary_file_on_failure(
    tmp_path: Path,
) -> None:
    """A write that can't replace the target leaves nothing behind.

    Args:
        tmp_path: Pytest temporary directory.
    """
    target = tmp_path / "occupied"
    target.mkdir()

    with pytest.raises(OSError, match=re.escape(target.name)):
        write_atomically(target, "text")

    assert list(tmp_path.iterdir()) == [target]
