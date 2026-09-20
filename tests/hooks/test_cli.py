# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the command-line installer that installs several agents at once."""

import json
import shlex
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.hooks import cli, installation

AGENTS = ("claude", "codex", "gemini")
# Installation makes the interpreter path absolute, so a stubbed one is already
# absolute in the host's own flavour and the expected command stays exact.
VENV_PYTHON = str(Path("/venv/bin/python").absolute())


def _run(workspace: Path, argv: list[str]) -> int:
    """Run the installer in a workspace with a stubbed hook environment.

    Args:
        workspace: Workspace the installer writes into.
        argv: Arguments passed to the installer.

    Returns:
        How many times the hooks environment was built.
    """
    with (
        patch.object(Path, "cwd", return_value=workspace),
        patch.object(
            installation, "setup_venv", return_value=Path(VENV_PYTHON)
        ) as setup_venv,
        patch.object(installation.os, "name", "posix"),
    ):
        cli.main(argv)
    return setup_venv.call_count


def test_installing_every_agent_builds_one_hook_environment(tmp_path: Path) -> None:
    """Agents installed together must share a single hooks environment.

    Args:
        tmp_path: Pytest temporary directory.
    """
    builds = _run(tmp_path, list(AGENTS))

    assert builds == 1
    for agent in AGENTS:
        installer = cli.INSTALLERS[agent]
        settings = json.loads((tmp_path / installer.settings_path).read_text())
        assert set(settings["hooks"]) == set(installer.handlers)


def test_repeated_agent_is_installed_once(tmp_path: Path) -> None:
    """Naming an agent twice must not register its handlers twice.

    Args:
        tmp_path: Pytest temporary directory.
    """
    _run(tmp_path, ["claude", "claude"])

    installer = cli.INSTALLERS["claude"]
    settings = json.loads((tmp_path / installer.settings_path).read_text())
    for groups in settings["hooks"].values():
        assert [handler for group in groups for handler in group["hooks"]] == [
            {
                "type": "command",
                "command": shlex.join([VENV_PYTHON, "-m", installer.module]),
                "timeout": 3,
            }
        ]


@pytest.mark.parametrize("argv", [[], ["claude", "unknown"]])
def test_missing_or_unknown_agent_is_rejected(tmp_path: Path, argv: list[str]) -> None:
    """The installer must reject an empty or unknown agent list.

    Args:
        tmp_path: Pytest temporary directory.
        argv: The case's arguments.
    """
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, argv)

    assert exit_info.value.code == 2
    assert not list(tmp_path.iterdir())


def test_invalid_settings_of_one_agent_stops_every_install(tmp_path: Path) -> None:
    """One invalid settings file must stop the run before any agent is written.

    Args:
        tmp_path: Pytest temporary directory.
    """
    codex_settings = tmp_path / cli.INSTALLERS["codex"].settings_path
    codex_settings.parent.mkdir()
    codex_settings.write_text("{")

    with (
        patch.object(Path, "cwd", return_value=tmp_path),
        patch.object(installation, "setup_venv") as setup_venv,
        pytest.raises(SystemExit) as exit_info,
    ):
        cli.main(["claude", "codex"])

    assert exit_info.value.code == 1
    setup_venv.assert_not_called()
    assert codex_settings.read_text() == "{"
    assert not (tmp_path / cli.INSTALLERS["claude"].settings_path).exists()
