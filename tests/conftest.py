# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Shared test fixtures."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Keep every test away from the real home directory and VAUXHALL_* variables.

    The dashboard reads and writes per-user files under ``~/.config/vauxhall``.

    Args:
        tmp_path_factory: Pytest temporary directory factory.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The temporary home directory.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", lambda: home)
    for name in list(os.environ):
        if name.startswith("VAUXHALL_"):
            monkeypatch.delenv(name)
    return home


@pytest.fixture(autouse=True)
def isolated_tempdir(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Keep hook state files out of the shared system temporary directory.

    The hooks record tool timings, assistant message chunks, and transcript
    cursors under ``tempfile.gettempdir()``, keyed by workspace and session, so
    one test's leftovers would otherwise reach another test using the same key.

    Args:
        tmp_path_factory: Pytest temporary directory factory.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The temporary directory standing in for the system one.
    """
    directory = tmp_path_factory.mktemp("systmp")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(directory))
    return directory


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run a test in an empty working directory, so no configuration file is there.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The empty working directory.
    """
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd
