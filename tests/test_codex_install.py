# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the Vauxhall Codex hook installer."""

import base64
import importlib
import json
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


def _installer() -> ModuleType:
    """Import the installer so a missing module is reported as a test failure."""
    return importlib.import_module("vauxhall.hooks.codex.install")


def test_load_hooks_creates_backup(tmp_path: Path) -> None:
    """Loading existing Codex hooks must preserve a backup."""
    hooks_file = tmp_path / "hooks.json"
    hooks_file.write_text('{"description": "existing", "hooks": {}}')

    hooks = _installer().load_hooks(hooks_file)

    assert hooks == {"description": "existing", "hooks": {}}
    assert (tmp_path / "hooks.json.bak").read_text() == hooks_file.read_text()


def test_purge_vauxhall_hooks_preserves_other_commands() -> None:
    """Purging must remove only Vauxhall's Codex command handlers."""
    hooks = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "python custom.py"},
                        {
                            "type": "command",
                            "command": (
                                "python -m vauxhall.hooks.codex.telemetry_hook"
                            ),
                        },
                    ],
                }
            ]
        }
    }

    _installer().purge_vauxhall_hooks(hooks)

    assert hooks["hooks"]["PreToolUse"] == [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "python custom.py"}],
        }
    ]


def test_hook_command_uses_posix_shell_quoting() -> None:
    """POSIX hook commands must quote metacharacters in the Python path."""
    installer = _installer()
    python = Path("/opt/Vauxhall $(touch marker)/bin/python")

    with patch.object(installer.os, "name", "posix"):
        command = installer.build_hook_command(python)

    assert command == (
        "'/opt/Vauxhall $(touch marker)/bin/python' "
        "-m vauxhall.hooks.codex.telemetry_hook"
    )


def test_hook_command_uses_windows_argument_quoting() -> None:
    """Windows hook commands must encode shell metacharacters in Python paths."""
    installer = _installer()
    python = Path("/Program Files/Vauxhall & %TEMP%/(owner's)/python.exe")

    with patch.object(installer.os, "name", "nt"):
        command = installer.build_hook_command(python)

    prefix = "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
    assert command.startswith(prefix)
    encoded_script = command.removeprefix(prefix)
    script = base64.b64decode(encoded_script).decode("utf-16-le")
    assert script == (
        "& '/Program Files/Vauxhall & %TEMP%/(owner''s)/python.exe' "
        "-m vauxhall.hooks.codex.telemetry_hook"
    )


def test_install_writes_project_codex_hooks(tmp_path: Path) -> None:
    """Installation must register every supported event in the project config."""
    installer = _installer()
    expected_events = {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "Stop",
        "Interrupt",
        "SessionEnd",
    }

    with (
        patch.object(installer.Path, "cwd", return_value=tmp_path),
        patch.object(
            installer,
            "setup_venv",
            return_value=Path("/venv/bin/python"),
        ),
    ):
        installer.install()

    hooks_file = tmp_path / ".codex" / "hooks.json"
    config = json.loads(hooks_file.read_text())
    assert set(config["hooks"]) == expected_events
    for groups in config["hooks"].values():
        assert groups == [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "/venv/bin/python -m vauxhall.hooks.codex.telemetry_hook"
                        ),
                        "statusMessage": "Sending Vauxhall telemetry",
                        "timeout": 3,
                    }
                ],
            }
        ]


@pytest.mark.parametrize("existing_content", ["{", "[]"])
def test_install_preserves_and_rejects_invalid_existing_hooks(
    tmp_path: Path, existing_content: str
) -> None:
    """Invalid existing hooks must be backed up and left unchanged."""
    installer = _installer()
    hooks_file = tmp_path / ".codex" / "hooks.json"
    hooks_file.parent.mkdir()
    hooks_file.write_text(existing_content)

    with (
        patch.object(installer.Path, "cwd", return_value=tmp_path),
        patch.object(installer, "setup_venv") as setup_venv,
        pytest.raises(SystemExit),
    ):
        installer.install()

    assert hooks_file.read_text() == existing_content
    assert hooks_file.with_suffix(".json.bak").read_text() == existing_content
    setup_venv.assert_not_called()


@pytest.mark.parametrize(
    "existing_config",
    [
        {"hooks": []},
        {"hooks": {"PreToolUse": {}}},
        {"hooks": {"PreToolUse": ["not-a-group"]}},
        {"hooks": {"PreToolUse": [{}]}},
        {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": {}}]}},
        {"hooks": {"PreToolUse": [{"hooks": ["not-a-handler"]}]}},
    ],
)
def test_install_rejects_invalid_nested_hook_config(
    tmp_path: Path, existing_config: dict
) -> None:
    """Invalid nested hook structures must be rejected before environment setup."""
    installer = _installer()
    hooks_file = tmp_path / ".codex" / "hooks.json"
    hooks_file.parent.mkdir()
    original = json.dumps(existing_config)
    hooks_file.write_text(original)

    with (
        patch.object(installer.Path, "cwd", return_value=tmp_path),
        patch.object(installer, "setup_venv") as setup_venv,
        pytest.raises(SystemExit),
    ):
        installer.install()

    assert hooks_file.read_text() == original
    assert hooks_file.with_suffix(".json.bak").read_text() == original
    setup_venv.assert_not_called()
