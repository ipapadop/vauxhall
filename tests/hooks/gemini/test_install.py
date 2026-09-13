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


def _handlers(settings: dict, event: str) -> list[dict]:
    """Return every handler registered for one Gemini event."""
    return [
        handler
        for group in settings["hooks"].get(event, [])
        for handler in group["hooks"]
    ]


def _install(tmp_path: Path, venv_python: Path, os_name: str = "posix") -> None:
    """Run the installer in a workspace with a stubbed hook environment."""
    with (
        patch.object(installer.Path, "cwd", return_value=tmp_path),
        patch.object(installer, "setup_venv", return_value=venv_python),
        patch.object(installer.common.os, "name", os_name),
    ):
        installer.install()


def test_purge_removes_only_generated_vauxhall_handlers() -> None:
    """Purging must match generated commands, not every vauxhall- name."""
    generated = {
        "name": "vauxhall-acting",
        "type": "command",
        "command": "/venv/bin/python -m vauxhall.hooks.gemini.telemetry_hook",
    }
    legacy = {
        "name": "vauxhall-acting",
        "type": "command",
        "command": "/venv/bin/python /src/vauxhall/hooks/gemini/telemetry_hook.py",
    }
    user_prefixed = {
        "name": "vauxhall-custom",
        "type": "command",
        "command": "python custom.py",
    }
    user_named_like_vauxhall = {
        "name": "vauxhall-acting",
        "type": "command",
        "command": "python custom.py",
    }
    settings = {
        "hooks": {
            "BeforeTool": [
                {
                    "matcher": "*",
                    "hooks": [
                        generated,
                        legacy,
                        user_prefixed,
                        user_named_like_vauxhall,
                    ],
                }
            ],
            "AfterTool": [{"matcher": "*", "hooks": [generated]}],
        }
    }

    installer.purge_vauxhall_hooks(settings)

    assert settings == {
        "hooks": {
            "BeforeTool": [
                {"matcher": "*", "hooks": [user_prefixed, user_named_like_vauxhall]}
            ]
        }
    }


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "python -c \"print('vauxhall.hooks.gemini.telemetry_hook')\"",
            id="mentions-module",
        ),
        pytest.param("echo -m vauxhall.hooks.gemini.telemetry_hook", id="not-python"),
        pytest.param(
            "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
            + base64.b64encode(
                "& 'Write-Output' -m vauxhall.hooks.gemini.telemetry_hook".encode(
                    "utf-16-le"
                )
            ).decode(),
            id="windows-not-python",
        ),
    ],
)
def test_purge_preserves_commands_that_are_not_generated(command: str) -> None:
    """Commands without the generated invocation shape must remain."""
    handler = {"name": "vauxhall-acting", "type": "command", "command": command}
    settings = {"hooks": {"BeforeTool": [{"matcher": "*", "hooks": [handler]}]}}

    installer.purge_vauxhall_hooks(settings)

    assert _handlers(settings, "BeforeTool") == [handler]


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


@pytest.mark.parametrize("existing_content", ["{", "[]", '// comment\n{"a": 1}'])
def test_install_preserves_and_rejects_invalid_existing_settings(
    tmp_path: Path, existing_content: str
) -> None:
    """Invalid existing settings must be backed up and left unchanged."""
    settings_file = tmp_path / ".gemini" / "settings.json"
    settings_file.parent.mkdir()
    settings_file.write_text(existing_content)

    with (
        patch.object(installer.Path, "cwd", return_value=tmp_path),
        patch.object(installer, "setup_venv") as setup_venv,
        pytest.raises(SystemExit) as exit_info,
    ):
        installer.install()

    assert exit_info.value.code == 1
    assert settings_file.read_text() == existing_content
    assert settings_file.with_suffix(".json.bak").read_text() == existing_content
    setup_venv.assert_not_called()


@pytest.mark.parametrize(
    "existing_settings",
    [
        {"hooks": []},
        {"hooks": {"BeforeTool": {}}},
        {"hooks": {"BeforeTool": ["not-a-group"]}},
        {"hooks": {"BeforeTool": [{}]}},
        {"hooks": {"BeforeTool": [{"matcher": "*", "hooks": {}}]}},
        {"hooks": {"BeforeTool": [{"hooks": ["not-a-handler"]}]}},
        {"hooks": {"CustomEvent": [{"hooks": [None]}]}},
    ],
)
def test_install_rejects_invalid_nested_settings(
    tmp_path: Path, existing_settings: dict
) -> None:
    """Invalid nested structures must be rejected before environment setup."""
    settings_file = tmp_path / ".gemini" / "settings.json"
    settings_file.parent.mkdir()
    original = json.dumps(existing_settings)
    settings_file.write_text(original)

    with (
        patch.object(installer.Path, "cwd", return_value=tmp_path),
        patch.object(installer, "setup_venv") as setup_venv,
        pytest.raises(SystemExit),
    ):
        installer.install()

    assert settings_file.read_text() == original
    assert settings_file.with_suffix(".json.bak").read_text() == original
    setup_venv.assert_not_called()


def test_reinstall_is_idempotent_and_preserves_unrelated_settings(
    tmp_path: Path,
) -> None:
    """Repeated installation must converge and keep user settings and hooks."""
    settings_file = tmp_path / ".gemini" / "settings.json"
    settings_file.parent.mkdir()
    user_handler = {
        "name": "vauxhall-custom",
        "type": "command",
        "command": "python custom.py",
    }
    settings_file.write_text(
        json.dumps(
            {
                "theme": "dark",
                "hooks": {
                    "enabled": True,
                    "disabled": ["other-hook"],
                    "BeforeTool": [
                        {"matcher": "run_shell_command", "hooks": [user_handler]}
                    ],
                },
            }
        )
    )
    venv_python = Path("/opt/Vauxhall $(touch marker)/bin/python")

    _install(tmp_path, venv_python)
    first = settings_file.read_text()
    _install(tmp_path, venv_python)

    assert settings_file.read_text() == first
    settings = json.loads(first)
    assert settings["theme"] == "dark"
    assert settings["hooks"]["enabled"] is True
    assert settings["hooks"]["disabled"] == ["other-hook"]
    assert user_handler in _handlers(settings, "BeforeTool")
    for event in installer.HOOK_CONFIGS:
        commands = [
            handler["command"]
            for handler in _handlers(settings, event)
            if installer.common.is_hook_handler(handler, installer.HOOK_MODULE)
        ]
        assert len(commands) == 1
        assert installer.common.shlex.split(commands[0]) == [
            str(venv_python),
            "-m",
            installer.HOOK_MODULE,
        ]
    assert not list(settings_file.parent.glob("*.tmp"))
    assert json.loads(settings_file.with_suffix(".json.bak").read_text()) == settings


def test_reinstall_replaces_legacy_source_checkout_handlers(tmp_path: Path) -> None:
    """Handlers that ran the hook from a source checkout must be replaced."""
    settings_file = tmp_path / ".gemini" / "settings.json"
    settings_file.parent.mkdir()
    legacy_handler = {
        "name": "vauxhall-acting",
        "type": "command",
        "command": "/old/venv/bin/python /src/vauxhall/hooks/gemini/telemetry_hook.py",
        "description": "Vauxhall telemetry for Gemini tool execution",
    }
    settings_file.write_text(
        json.dumps(
            {"hooks": {"BeforeTool": [{"matcher": "*", "hooks": [legacy_handler]}]}}
        )
    )

    _install(tmp_path, Path("/venv/bin/python"))

    settings = json.loads(settings_file.read_text())
    assert _handlers(settings, "BeforeTool") == [
        {
            "name": "vauxhall-acting",
            "type": "command",
            "command": "/venv/bin/python -m vauxhall.hooks.gemini.telemetry_hook",
            "description": "Vauxhall telemetry for Gemini tool execution",
        }
    ]


def test_windows_reinstall_replaces_only_vauxhall_handlers(tmp_path: Path) -> None:
    """Repeated Windows installation must replace only generated handlers."""
    settings_file = tmp_path / ".gemini" / "settings.json"
    settings_file.parent.mkdir()
    prefix = "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
    custom_script = "& 'C:/custom/python.exe' -m custom.telemetry"
    custom_handler = {
        "name": "vauxhall-custom",
        "type": "command",
        "command": prefix
        + base64.b64encode(custom_script.encode("utf-16-le")).decode(),
    }
    settings_file.write_text(
        json.dumps(
            {"hooks": {"BeforeTool": [{"matcher": "*", "hooks": [custom_handler]}]}}
        )
    )
    venv_python = Path("C:/Program Files/Vauxhall & %TEMP%/(owner's)/python.exe")

    _install(tmp_path, venv_python, os_name="nt")
    _install(tmp_path, venv_python, os_name="nt")

    settings = json.loads(settings_file.read_text())
    for event in installer.HOOK_CONFIGS:
        scripts = [
            base64.b64decode(handler["command"].removeprefix(prefix)).decode(
                "utf-16-le"
            )
            for handler in _handlers(settings, event)
            if handler["command"].startswith(prefix)
        ]
        assert sum(installer.HOOK_MODULE in script for script in scripts) == 1
    assert _handlers(settings, "BeforeTool")[0] == custom_handler


def test_failed_write_leaves_existing_settings_unchanged(tmp_path: Path) -> None:
    """A failure while replacing settings must not truncate the original file."""
    settings_file = tmp_path / ".gemini" / "settings.json"
    settings_file.parent.mkdir()
    original = json.dumps({"theme": "dark"})
    settings_file.write_text(original)

    with (
        patch.object(installer.common.Path, "replace", side_effect=OSError("full")),
        pytest.raises(SystemExit) as exit_info,
    ):
        _install(tmp_path, Path("/venv/bin/python"))

    assert exit_info.value.code == 1
    assert settings_file.read_text() == original
    assert not list(settings_file.parent.glob("*.tmp"))
