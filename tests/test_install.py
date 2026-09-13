# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the Vauxhall hook installer."""

import base64
import json
from pathlib import Path
from unittest.mock import call, patch

import pytest

from vauxhall.hooks.gemini import install as installer


def test_load_settings(tmp_path: Path) -> None:
    """Verify load_settings creates backup and returns dict."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"existing": "value"}')

    settings = installer.load_settings(settings_file)
    assert settings == {"existing": "value"}
    assert (tmp_path / "settings.json.bak").exists()


def test_load_settings_empty(tmp_path: Path) -> None:
    """Verify load_settings returns empty dict if file is missing."""
    settings_file = tmp_path / "settings.json"
    settings = installer.load_settings(settings_file)
    assert settings == {}


def test_purge_vauxhall_hooks() -> None:
    """Verify purge_vauxhall_hooks removes old vauxhall hooks."""
    settings = {
        "hooks": {
            "BeforeAgent": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"name": "vauxhall-acting"},
                        {"name": "user-custom-hook"},
                    ],
                }
            ]
        }
    }
    installer.purge_vauxhall_hooks(settings)
    assert len(settings["hooks"]["BeforeAgent"][0]["hooks"]) == 1
    assert settings["hooks"]["BeforeAgent"][0]["hooks"][0]["name"] == "user-custom-hook"


def test_register_hook() -> None:
    """Verify register_hook appends or updates correctly."""
    settings = {}
    config = {"name": "vauxhall-test", "description": "Test hook"}
    command = "python test.py"

    installer.register_hook(settings, "AfterAgent", config, command)

    assert "AfterAgent" in settings["hooks"]
    assert settings["hooks"]["AfterAgent"][0]["matcher"] == "*"

    hook = settings["hooks"]["AfterAgent"][0]["hooks"][0]
    assert hook["name"] == "vauxhall-test"
    assert hook["command"] == command


def test_hook_command_uses_posix_module_invocation() -> None:
    """Gemini hooks must use the installed module with safe POSIX quoting."""
    python = Path("/opt/Vauxhall $(touch marker)/bin/python")

    with patch.object(installer.common.os, "name", "posix"):
        command = installer.build_hook_command(python)

    assert command == (
        "'/opt/Vauxhall $(touch marker)/bin/python' "
        "-m vauxhall.hooks.gemini.telemetry_hook"
    )


def test_hook_command_uses_windows_module_invocation() -> None:
    """Gemini hooks must encode Windows paths and execute the installed module."""
    python = Path("/Program Files/Vauxhall & %TEMP%/(owner's)/python.exe")

    with patch.object(installer.common.os, "name", "nt"):
        command = installer.build_hook_command(python)

    prefix = "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
    assert command.startswith(prefix)
    encoded_script = command.removeprefix(prefix)
    script = base64.b64decode(encoded_script).decode("utf-16-le")
    assert script == (
        "& '/Program Files/Vauxhall & %TEMP%/(owner''s)/python.exe' "
        "-m vauxhall.hooks.gemini.telemetry_hook"
    )


def test_setup_venv_installs_exact_distribution_version(tmp_path: Path) -> None:
    """Gemini hook environments must install an immutable published release."""
    venv_dir = tmp_path / "hooks-venv"
    if installer.common.os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    with patch.object(installer.common.subprocess, "run") as run:
        result = installer.setup_venv(venv_dir)

    assert result == venv_python
    assert run.call_args_list == [
        call(
            [installer.sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
        ),
        call(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "vauxhall[hooks]==0.1.0",
            ],
            check=True,
            capture_output=True,
        ),
    ]


def test_install_registers_session_end_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gemini installation must register Vauxhall's SessionEnd lifecycle hook."""
    monkeypatch.chdir(tmp_path)
    venv_python = tmp_path / ".vauxhall-venv" / "bin" / "python"

    with patch.object(installer, "setup_venv", return_value=venv_python):
        installer.install()

    settings = json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    session_end_hooks = settings["hooks"]["SessionEnd"][0]["hooks"]
    assert session_end_hooks == [
        {
            "name": "vauxhall-session-end",
            "type": "command",
            "command": installer.build_hook_command(venv_python.absolute()),
            "description": "Vauxhall telemetry for Gemini session end",
        }
    ]
