# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the Vauxhall Claude Code hook installer."""

import base64
import json
import shlex
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.hooks.claude import install as installer

WINDOWS_PREFIX = "powershell.exe -NoProfile -NonInteractive -EncodedCommand "


def _settings_file(workspace: Path) -> Path:
    """Return the settings file the installer writes."""
    return workspace / ".claude" / "settings.local.json"


def _handlers(settings: dict, event: str) -> list[dict]:
    """Return every handler registered for one Claude Code event."""
    return [
        handler
        for group in settings["hooks"].get(event, [])
        for handler in group["hooks"]
    ]


def _install(workspace: Path, venv_python: Path, os_name: str = "posix") -> None:
    """Run the installer in a workspace with a stubbed hook environment."""
    with (
        patch.object(installer.Path, "cwd", return_value=workspace),
        patch.object(installer, "setup_venv", return_value=venv_python),
        patch.object(installer.common.os, "name", os_name),
    ):
        installer.install()


def test_install_writes_local_claude_settings(tmp_path: Path) -> None:
    """Installation must register every supported event in local settings."""
    _install(tmp_path, Path("/venv/bin/python"))

    settings = json.loads(_settings_file(tmp_path).read_text())
    assert set(settings["hooks"]) == set(installer.HOOK_EVENTS)
    for groups in settings["hooks"].values():
        assert groups == [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "/venv/bin/python -m vauxhall.hooks.claude.telemetry_hook"
                        ),
                        "timeout": 3,
                    }
                ],
            }
        ]


def test_hook_command_quotes_posix_metacharacters() -> None:
    """POSIX hook commands must quote metacharacters in the Python path."""
    python = Path("/opt/Vauxhall $(touch marker)/bin/python")

    with patch.object(installer.common.os, "name", "posix"):
        command = installer.build_hook_command(python)

    assert shlex.split(command) == [str(python), "-m", installer.HOOK_MODULE]


def test_hook_command_encodes_windows_metacharacters() -> None:
    """Windows hook commands must encode shell metacharacters in Python paths."""
    python = Path("/Program Files/Vauxhall & %TEMP%/(owner's)/python.exe")

    with patch.object(installer.common.os, "name", "nt"):
        command = installer.build_hook_command(python)

    script = base64.b64decode(command.removeprefix(WINDOWS_PREFIX)).decode("utf-16-le")
    assert script == (
        "& '/Program Files/Vauxhall & %TEMP%/(owner''s)/python.exe' "
        "-m vauxhall.hooks.claude.telemetry_hook"
    )


@pytest.mark.parametrize("existing_content", ["{", "[]"])
def test_install_preserves_and_rejects_invalid_existing_settings(
    tmp_path: Path, existing_content: str
) -> None:
    """Invalid existing settings must be backed up and left unchanged."""
    settings_file = _settings_file(tmp_path)
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
        {"hooks": {"PreToolUse": {}}},
        {"hooks": {"PreToolUse": ["not-a-group"]}},
        {"hooks": {"PreToolUse": [{"matcher": "Bash"}]}},
        {"hooks": {"PreToolUse": [{"hooks": ["not-a-handler"]}]}},
    ],
)
def test_install_rejects_invalid_nested_settings(
    tmp_path: Path, existing_settings: dict
) -> None:
    """Invalid nested structures must be rejected before environment setup."""
    settings_file = _settings_file(tmp_path)
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
    setup_venv.assert_not_called()


def test_reinstall_is_idempotent_and_preserves_unrelated_settings(
    tmp_path: Path,
) -> None:
    """Repeated installation must converge and keep user settings and hooks."""
    settings_file = _settings_file(tmp_path)
    settings_file.parent.mkdir()
    user_handler = {"type": "command", "command": "python lint.py"}
    mentions_module = {
        "type": "command",
        "command": "echo -m vauxhall.hooks.claude.telemetry_hook",
    }
    settings_file.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(git status)"]},
                "hooks": {
                    "PostToolUse": [
                        {"matcher": "Edit", "hooks": [user_handler, mentions_module]}
                    ]
                },
            }
        )
    )

    _install(tmp_path, Path("/venv/bin/python"))
    first = settings_file.read_text()
    _install(tmp_path, Path("/venv/bin/python"))

    assert settings_file.read_text() == first
    settings = json.loads(first)
    assert settings["permissions"] == {"allow": ["Bash(git status)"]}
    assert settings["hooks"]["PostToolUse"][0] == {
        "matcher": "Edit",
        "hooks": [user_handler, mentions_module],
    }
    for event in installer.HOOK_EVENTS:
        generated = [
            handler
            for handler in _handlers(settings, event)
            if installer.common.is_hook_handler(handler, installer.HOOK_MODULE)
        ]
        assert len(generated) == 1


def test_windows_reinstall_replaces_only_vauxhall_handlers(tmp_path: Path) -> None:
    """Repeated Windows installation must replace only generated handlers."""
    custom_script = "& 'C:/custom/python.exe' -m custom.telemetry"
    custom_handler = {
        "type": "command",
        "command": WINDOWS_PREFIX
        + base64.b64encode(custom_script.encode("utf-16-le")).decode(),
    }
    settings_file = _settings_file(tmp_path)
    settings_file.parent.mkdir()
    settings_file.write_text(
        json.dumps({"hooks": {"Stop": [{"matcher": "*", "hooks": [custom_handler]}]}})
    )

    _install(tmp_path, Path("C:/Vauxhall/python.exe"), os_name="nt")
    _install(tmp_path, Path("C:/Vauxhall/python.exe"), os_name="nt")

    settings = json.loads(settings_file.read_text())
    for event in installer.HOOK_EVENTS:
        scripts = [
            base64.b64decode(handler["command"].removeprefix(WINDOWS_PREFIX)).decode(
                "utf-16-le"
            )
            for handler in _handlers(settings, event)
        ]
        assert sum(installer.HOOK_MODULE in script for script in scripts) == 1
    assert _handlers(settings, "Stop")[0] == custom_handler


def test_failed_write_leaves_existing_settings_unchanged(tmp_path: Path) -> None:
    """A failure while replacing settings must not truncate the original file."""
    settings_file = _settings_file(tmp_path)
    settings_file.parent.mkdir()
    original = json.dumps({"model": "opus"})
    settings_file.write_text(original)

    with (
        patch.object(installer.common.Path, "replace", side_effect=OSError("full")),
        pytest.raises(SystemExit),
    ):
        _install(tmp_path, Path("/venv/bin/python"))

    assert settings_file.read_text() == original
    assert not list(settings_file.parent.glob("*.tmp"))
