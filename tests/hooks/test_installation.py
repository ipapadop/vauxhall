# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the shared hook installation helpers and the agent installers."""

import base64
import json
import shlex
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import call, patch

import pytest

from vauxhall.hooks import installation
from vauxhall.hooks.claude import install as claude_install
from vauxhall.hooks.codex import install as codex_install
from vauxhall.hooks.gemini import install as gemini_install

PREFIX = installation.WINDOWS_ENCODED_COMMAND_PREFIX
MODULE = "vauxhall.hooks.codex.telemetry_hook"
INSTALLERS = pytest.mark.parametrize(
    "installer",
    [
        pytest.param(claude_install, id="claude"),
        pytest.param(codex_install, id="codex"),
        pytest.param(gemini_install, id="gemini"),
    ],
)


def _encode(script: str) -> str:
    """Return a Windows encoded command that runs a PowerShell script."""
    return PREFIX + base64.b64encode(script.encode("utf-16-le")).decode()


def _decode(command: str) -> str:
    """Return the PowerShell script inside a Windows encoded command."""
    return base64.b64decode(command.removeprefix(PREFIX)).decode("utf-16-le")


def _handlers(settings: dict, event: str) -> list[dict]:
    """Return every handler registered for one event."""
    return [
        handler
        for group in settings["hooks"].get(event, [])
        for handler in group["hooks"]
    ]


def _settings_file(installer: ModuleType, workspace: Path) -> Path:
    """Return the settings file an installer writes in a workspace."""
    return workspace / installer.SETTINGS_PATH


def _install(
    installer: ModuleType,
    workspace: Path,
    venv_python: str = "/venv/bin/python",
    os_name: str = "posix",
) -> None:
    """Run an installer in a workspace with a stubbed hook environment."""
    with (
        patch.object(Path, "cwd", return_value=workspace),
        patch.object(installation, "setup_venv", return_value=Path(venv_python)),
        patch.object(installation.os, "name", os_name),
    ):
        installer.install()


def test_hook_command_quotes_posix_metacharacters() -> None:
    """POSIX hook commands must quote metacharacters in the Python path."""
    python = Path("/opt/Vauxhall $(touch marker)/bin/python")

    with patch.object(installation.os, "name", "posix"):
        command = installation.build_hook_command(python, MODULE)

    assert command == f"'/opt/Vauxhall $(touch marker)/bin/python' -m {MODULE}"


def test_hook_command_encodes_windows_metacharacters() -> None:
    """Windows hook commands must encode shell metacharacters in Python paths."""
    python = Path("/Program Files/Vauxhall & %TEMP%/(owner's)/python.exe")

    with patch.object(installation.os, "name", "nt"):
        command = installation.build_hook_command(python, MODULE)

    assert command.startswith(PREFIX)
    assert _decode(command) == (
        f"& '/Program Files/Vauxhall & %TEMP%/(owner''s)/python.exe' -m {MODULE}"
    )


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"/venv/bin/python -m {MODULE}", id="posix"),
        pytest.param(_encode(f"& 'C:/Vauxhall/python.exe' -m {MODULE}"), id="windows"),
    ],
)
def test_is_hook_handler_matches_generated_commands(command: str) -> None:
    """Generated invocations of the hook module must be recognized."""
    handler = {"type": "command", "command": command}

    assert installation.is_hook_handler(handler, MODULE)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"python -c \"print('{MODULE}')\"", id="mentions-module"),
        pytest.param(f"echo -m {MODULE}", id="not-python"),
        pytest.param(f"/venv/bin/python -m {MODULE}.other", id="other-module"),
        pytest.param(
            _encode(f"Write-Output '{MODULE} is configured'"),
            id="windows-mentions-module",
        ),
        pytest.param(_encode(f"& 'Write-Output' -m {MODULE}"), id="windows-not-python"),
    ],
)
def test_is_hook_handler_ignores_other_commands(command: str) -> None:
    """Commands without the generated invocation shape must not be owned."""
    handler = {"type": "command", "command": command}

    assert not installation.is_hook_handler(handler, MODULE)


def test_load_hook_settings_backs_up_existing_file(tmp_path: Path) -> None:
    """Loading existing settings must preserve a backup."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"existing": "value"}')

    assert installation.load_hook_settings(settings_file, "Agent") == {
        "existing": "value"
    }
    assert settings_file.with_suffix(".json.bak").read_text() == (
        settings_file.read_text()
    )


def test_load_hook_settings_returns_empty_settings_when_missing(
    tmp_path: Path,
) -> None:
    """A missing settings file loads as empty settings."""
    assert installation.load_hook_settings(tmp_path / "settings.json", "Agent") == {}


def test_register_hook_handler_uses_catch_all_group() -> None:
    """Handlers must be appended to the event's catch-all matcher group."""
    settings = {"hooks": {"Stop": [{"matcher": "Bash", "hooks": []}]}}

    installation.register_hook_handler(settings, "Stop", {"type": "command"})
    installation.register_hook_handler(settings, "Stop", {"type": "other"})

    assert settings["hooks"]["Stop"] == [
        {"matcher": "Bash", "hooks": []},
        {"matcher": "*", "hooks": [{"type": "command"}, {"type": "other"}]},
    ]


def test_setup_venv_installs_exact_distribution_version(tmp_path: Path) -> None:
    """Hook environments must install an immutable published release."""
    venv_dir = tmp_path / "hooks-venv"
    if installation.os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    with patch.object(installation.subprocess, "run") as run:
        result = installation.setup_venv(venv_dir)

    assert result == venv_python
    assert run.call_args_list == [
        call([sys.executable, "-m", "venv", str(venv_dir)], check=True),
        call(
            [str(venv_python), "-m", "pip", "install", "vauxhall[hooks]==0.1.0"],
            check=True,
            capture_output=True,
        ),
    ]


@INSTALLERS
def test_install_registers_every_handler(installer: ModuleType, tmp_path: Path) -> None:
    """Installation must register each handler in a catch-all group."""
    _install(installer, tmp_path)

    settings = json.loads(_settings_file(installer, tmp_path).read_text())
    assert set(settings["hooks"]) == set(installer.HANDLERS)
    for event, fields in installer.HANDLERS.items():
        handler = {
            "type": "command",
            "command": f"/venv/bin/python -m {installer.HOOK_MODULE}",
            **fields,
        }
        assert settings["hooks"][event] == [{"matcher": "*", "hooks": [handler]}]


@INSTALLERS
@pytest.mark.parametrize("existing_content", ["{", "[]", '// comment\n{"a": 1}'])
def test_install_preserves_and_rejects_invalid_existing_settings(
    installer: ModuleType, tmp_path: Path, existing_content: str
) -> None:
    """Invalid existing settings must be backed up and left unchanged."""
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    settings_file.write_text(existing_content)

    with (
        patch.object(Path, "cwd", return_value=tmp_path),
        patch.object(installation, "setup_venv") as setup_venv,
        pytest.raises(SystemExit) as exit_info,
    ):
        installer.install()

    assert exit_info.value.code == 1
    assert settings_file.read_text() == existing_content
    assert settings_file.with_suffix(".json.bak").read_text() == existing_content
    setup_venv.assert_not_called()


@INSTALLERS
@pytest.mark.parametrize(
    "existing_settings",
    [
        {"hooks": []},
        {"hooks": {"CustomEvent": {}}},
        {"hooks": {"CustomEvent": ["not-a-group"]}},
        {"hooks": {"CustomEvent": [{}]}},
        {"hooks": {"CustomEvent": [{"matcher": "*", "hooks": {}}]}},
        {"hooks": {"CustomEvent": [{"hooks": ["not-a-handler"]}]}},
    ],
)
def test_install_rejects_invalid_nested_settings(
    installer: ModuleType, tmp_path: Path, existing_settings: dict
) -> None:
    """Invalid nested structures must be rejected before environment setup."""
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    original = json.dumps(existing_settings)
    settings_file.write_text(original)

    with (
        patch.object(Path, "cwd", return_value=tmp_path),
        patch.object(installation, "setup_venv") as setup_venv,
        pytest.raises(SystemExit),
    ):
        installer.install()

    assert settings_file.read_text() == original
    setup_venv.assert_not_called()


@INSTALLERS
def test_reinstall_is_idempotent_and_preserves_unrelated_settings(
    installer: ModuleType, tmp_path: Path
) -> None:
    """Repeated installation must converge and keep user settings and hooks."""
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    user_group = {
        "matcher": "custom",
        "hooks": [
            {"type": "command", "command": "python lint.py"},
            {"type": "command", "command": f"echo -m {installer.HOOK_MODULE}"},
        ],
    }
    settings_file.write_text(
        json.dumps({"theme": "dark", "hooks": {"CustomEvent": [user_group]}})
    )
    venv_python = "/opt/Vauxhall $(touch marker)/bin/python"

    _install(installer, tmp_path, venv_python)
    first = settings_file.read_text()
    _install(installer, tmp_path, venv_python)

    assert settings_file.read_text() == first
    settings = json.loads(first)
    assert settings["theme"] == "dark"
    assert settings["hooks"]["CustomEvent"] == [user_group]
    for event in installer.HANDLERS:
        commands = [
            shlex.split(handler["command"])
            for handler in _handlers(settings, event)
            if installation.is_hook_handler(handler, installer.HOOK_MODULE)
        ]
        assert commands == [[venv_python, "-m", installer.HOOK_MODULE]]
    assert not list(settings_file.parent.glob("*.tmp"))
    assert json.loads(settings_file.with_suffix(".json.bak").read_text()) == settings


@INSTALLERS
def test_windows_reinstall_replaces_only_vauxhall_handlers(
    installer: ModuleType, tmp_path: Path
) -> None:
    """Repeated Windows installation must replace only generated handlers."""
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    custom_handler = {
        "type": "command",
        "command": _encode("& 'C:/custom/python.exe' -m custom.telemetry"),
    }
    first_event = next(iter(installer.HANDLERS))
    settings_file.write_text(
        json.dumps(
            {"hooks": {first_event: [{"matcher": "*", "hooks": [custom_handler]}]}}
        )
    )
    venv_python = "C:/Program Files/Vauxhall & %TEMP%/(owner's)/python.exe"

    _install(installer, tmp_path, venv_python, os_name="nt")
    _install(installer, tmp_path, venv_python, os_name="nt")

    settings = json.loads(settings_file.read_text())
    for event in installer.HANDLERS:
        scripts = [
            _decode(handler["command"]) for handler in _handlers(settings, event)
        ]
        assert sum(installer.HOOK_MODULE in script for script in scripts) == 1
    assert _handlers(settings, first_event)[0] == custom_handler


@INSTALLERS
def test_failed_write_leaves_existing_settings_unchanged(
    installer: ModuleType, tmp_path: Path
) -> None:
    """A failure while replacing settings must not truncate the original file."""
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    original = json.dumps({"theme": "dark"})
    settings_file.write_text(original)

    with (
        patch.object(Path, "replace", side_effect=OSError("disk full")),
        pytest.raises(SystemExit) as exit_info,
    ):
        _install(installer, tmp_path)

    assert exit_info.value.code == 1
    assert settings_file.read_text() == original
    assert not list(settings_file.parent.glob("*.tmp"))
