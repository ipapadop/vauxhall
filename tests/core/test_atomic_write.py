# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for atomic file replacement."""

import json
import os
import re
import stat
from pathlib import Path

import pytest

from vauxhall.core.files import write_atomically, write_json_atomically

POSIX_MODES = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")


@pytest.mark.parametrize("durable", [True, False])
def test_write_atomically_replaces_the_file(tmp_path: Path, *, durable: bool) -> None:
    """The new text replaces the old, and no temporary file is left.

    Args:
        tmp_path: Pytest temporary directory.
        durable: Whether the write is flushed to disk.
    """
    path = tmp_path / "state"
    path.write_text("old", encoding="utf-8")

    write_atomically(path, "new", durable=durable)

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


def test_write_atomically_keeps_a_lone_surrogate(tmp_path: Path) -> None:
    """Text decoded from hook JSON can hold a lone surrogate.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "chunk"

    write_atomically(path, "a\udc80b", private=True)

    assert path.read_bytes().decode("utf-8", "surrogatepass") == "a\udc80b"


@POSIX_MODES
def test_private_write_is_owner_only(tmp_path: Path) -> None:
    """A private file is readable by its owner alone, whatever it replaces.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "chunk"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o644)

    write_atomically(path, "new", private=True)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@POSIX_MODES
def test_shared_write_keeps_the_existing_mode(tmp_path: Path) -> None:
    """Replacing a file the user made group-readable keeps it so.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o640)

    write_json_atomically(path, {"saved": True})

    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert path.read_text(encoding="utf-8") == '{\n  "saved": true\n}\n'


def test_write_json_atomically_replaces_a_symlink_unless_told_to_follow(
    tmp_path: Path,
) -> None:
    """A link is replaced by default and kept, with its target written, on request.

    Args:
        tmp_path: Pytest temporary directory.
    """
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    followed = tmp_path / "followed.json"
    replaced = tmp_path / "replaced.json"
    try:
        followed.symlink_to(target)
        replaced.symlink_to(target)
    except OSError:
        pytest.skip("creating symlinks needs a privilege on this platform")

    write_json_atomically(followed, {"followed": True}, follow_symlinks=True)
    assert followed.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"followed": True}

    write_json_atomically(replaced, {"replaced": True})
    assert not replaced.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8")) == {"followed": True}
