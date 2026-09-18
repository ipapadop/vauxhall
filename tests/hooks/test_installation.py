# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the shared hook installation helpers and the agent installers."""

import base64
import json
import shlex
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, call, patch

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
    """Return a Windows encoded command that runs a PowerShell script.

    Args:
        script: PowerShell script to encode.

    Returns:
        The encoded command.
    """
    return PREFIX + base64.b64encode(script.encode("utf-16-le")).decode()


def _decode(command: str) -> str:
    """Return the PowerShell script inside a Windows encoded command.

    Args:
        command: Windows encoded command to decode.

    Returns:
        The decoded script.
    """
    return base64.b64decode(command.removeprefix(PREFIX)).decode("utf-16-le")


def _handlers(settings: dict, event: str) -> list[dict]:
    """Return every handler registered for one event.

    Args:
        settings: The settings file's parsed contents.
        event: Hook event whose handlers are returned.

    Returns:
        The handlers registered for the event.
    """
    return [
        handler
        for group in settings["hooks"].get(event, [])
        for handler in group["hooks"]
    ]


def _settings_file(installer: ModuleType, workspace: Path) -> Path:
    """Return the settings file an installer writes in a workspace.

    Args:
        installer: Installer module whose settings path is used.
        workspace: Workspace the installer writes into.

    Returns:
        The path of the settings file.
    """
    return workspace / installer.SETTINGS_PATH


def _install(
    installer: ModuleType,
    workspace: Path,
    venv_python: str = "/venv/bin/python",
    os_name: str = "posix",
) -> None:
    """Run an installer in a workspace with a stubbed hook environment.

    Args:
        installer: Installer module to run.
        workspace: Workspace the installer writes into.
        venv_python: Python executable the generated command runs.
        os_name: Value ``os.name`` is stubbed with.
    """
    with (
        patch.object(Path, "cwd", return_value=workspace),
        patch.object(installation, "setup_venv", return_value=Path(venv_python)),
        patch.object(installation.os, "name", os_name),
    ):
        installation.install_hooks([installer.INSTALLER])


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
    """Generated invocations of the hook module must be recognized.

    Args:
        command: The case's command.
    """
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
    """Commands without the generated invocation shape must not be owned.

    Args:
        command: The case's command.
    """
    handler = {"type": "command", "command": command}

    assert not installation.is_hook_handler(handler, MODULE)


def test_load_hook_settings_backs_up_existing_file(tmp_path: Path) -> None:
    """Loading existing settings must preserve a backup.

    Args:
        tmp_path: Pytest temporary directory.
    """
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
    """A missing settings file loads as empty settings.

    Args:
        tmp_path: Pytest temporary directory.
    """
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
    """Hook environments must install an immutable published release.

    Args:
        tmp_path: Pytest temporary directory.
    """
    venv_dir = tmp_path / "hooks-venv"
    if installation.os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    with (
        patch.object(installation.subprocess, "run") as run,
        patch.object(
            installation.importlib.metadata,
            "distribution",
            side_effect=installation.importlib.metadata.PackageNotFoundError,
        ),
    ):
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
    """Installation must register each handler in a catch-all group.

    Args:
        installer: The installer module under test.
        tmp_path: Pytest temporary directory.
    """
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
    """Invalid existing settings must be backed up and left unchanged.

    Args:
        installer: The installer module under test.
        tmp_path: Pytest temporary directory.
        existing_content: Raw content already in the file.
    """
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    settings_file.write_text(existing_content)

    with (
        patch.object(Path, "cwd", return_value=tmp_path),
        patch.object(installation, "setup_venv") as setup_venv,
        pytest.raises(SystemExit) as exit_info,
    ):
        installation.install_hooks([installer.INSTALLER])

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
    """Invalid nested structures must be rejected before environment setup.

    Args:
        installer: The installer module under test.
        tmp_path: Pytest temporary directory.
        existing_settings: Settings already in the file.
    """
    settings_file = _settings_file(installer, tmp_path)
    settings_file.parent.mkdir()
    original = json.dumps(existing_settings)
    settings_file.write_text(original)

    with (
        patch.object(Path, "cwd", return_value=tmp_path),
        patch.object(installation, "setup_venv") as setup_venv,
        pytest.raises(SystemExit),
    ):
        installation.install_hooks([installer.INSTALLER])

    assert settings_file.read_text() == original
    setup_venv.assert_not_called()


@INSTALLERS
def test_reinstall_is_idempotent_and_preserves_unrelated_settings(
    installer: ModuleType, tmp_path: Path
) -> None:
    """Repeated installation must converge and keep user settings and hooks.

    Args:
        installer: The installer module under test.
        tmp_path: Pytest temporary directory.
    """
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
    """Repeated Windows installation must replace only generated handlers.

    Args:
        installer: The installer module under test.
        tmp_path: Pytest temporary directory.
    """
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
    """A failure while replacing settings must not truncate the original file.

    Args:
        installer: The installer module under test.
        tmp_path: Pytest temporary directory.
    """
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


@pytest.mark.parametrize(
    ("direct_url", "requirement"),
    [
        pytest.param(None, "vauxhall[hooks]==0.1.0", id="package-index"),
        pytest.param(
            {
                "url": "https://github.com/ipapadop/vauxhall.git",
                "vcs_info": {
                    "vcs": "git",
                    "commit_id": "0123abc",
                    "requested_revision": "main",
                },
            },
            "vauxhall[hooks] @ git+https://github.com/ipapadop/vauxhall.git@0123abc",
            id="git",
        ),
        pytest.param(
            {
                "url": "file:///src/vauxhall",
                "vcs_info": {"vcs": "git", "commit_id": "abc"},
            },
            "git+file:///src/vauxhall@abc",
            id="local-git",
        ),
        pytest.param(
            {"url": "file:///src/vauxhall", "dir_info": {"editable": True}},
            "vauxhall[hooks] @ file:///src/vauxhall",
            id="local-directory",
        ),
        pytest.param(
            {"url": "file:///dist/vauxhall-0.1.0-py3-none-any.whl", "archive_info": {}},
            "vauxhall[hooks] @ file:///dist/vauxhall-0.1.0-py3-none-any.whl",
            id="wheel",
        ),
        pytest.param(
            {
                "url": "https://example.com/mono.git",
                "vcs_info": {"vcs": "git", "commit_id": "abc"},
                "subdirectory": "python",
            },
            "vauxhall[hooks] @ git+https://example.com/mono.git@abc#subdirectory=python",
            id="subdirectory",
        ),
    ],
)
def test_hook_environment_installs_from_the_installer_source(
    direct_url: dict | None, requirement: str
) -> None:
    """Hook environments must install Vauxhall from where it was installed.

    Args:
        direct_url: The recorded PEP 610 source of the installation.
        requirement: The pip requirement the case expects.
    """
    distribution = MagicMock()
    distribution.read_text.return_value = (
        None if direct_url is None else json.dumps(direct_url)
    )

    with patch.object(
        installation.importlib.metadata, "distribution", return_value=distribution
    ):
        assert installation._hooks_requirement() == requirement
