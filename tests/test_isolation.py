# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the shared test isolation fixtures."""

import subprocess
import sys
from pathlib import Path


def test_subprocess_sees_isolated_home(isolated_home: Path) -> None:
    """A hook run as a child process must not reach the real home directory.

    Args:
        isolated_home: The temporary home directory from ``conftest.py``.
    """
    completed = subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; print(Path.home())"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert Path(completed.stdout.strip()) == isolated_home
