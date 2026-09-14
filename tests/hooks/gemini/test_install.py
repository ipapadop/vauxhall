# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the Gemini-specific behavior of the Vauxhall hook installer."""

import json
from pathlib import Path
from unittest.mock import patch

from vauxhall.hooks import installation
from vauxhall.hooks.gemini import install as installer


def _install(workspace: Path) -> dict:
    """Install into a workspace with a stubbed environment and return settings."""
    with (
        patch.object(Path, "cwd", return_value=workspace),
        patch.object(installation, "setup_venv", return_value=Path("/venv/bin/python")),
        patch.object(installation.os, "name", "posix"),
    ):
        installer.install()
    return json.loads((workspace / installer.SETTINGS_PATH).read_text())


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

    installation.purge_hook_handlers(
        settings, installer._is_vauxhall_handler, installer._HOOK_OPTION_KEYS
    )

    assert settings == {
        "hooks": {
            "BeforeTool": [
                {"matcher": "*", "hooks": [user_prefixed, user_named_like_vauxhall]}
            ]
        }
    }


def test_reinstall_keeps_hook_options(tmp_path: Path) -> None:
    """Hook-system options stored beside events must be preserved."""
    settings_file = tmp_path / installer.SETTINGS_PATH
    settings_file.parent.mkdir()
    options = {"enabled": True, "disabled": ["other-hook"], "notifications": False}
    settings_file.write_text(json.dumps({"hooks": options}))

    settings = _install(tmp_path)

    assert {key: settings["hooks"][key] for key in options} == options


def test_reinstall_replaces_legacy_source_checkout_handlers(tmp_path: Path) -> None:
    """Handlers that ran the hook from a source checkout must be replaced."""
    settings_file = tmp_path / installer.SETTINGS_PATH
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

    settings = _install(tmp_path)

    assert settings["hooks"]["BeforeTool"] == [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "/venv/bin/python -m vauxhall.hooks.gemini.telemetry_hook"
                    ),
                    "name": "vauxhall-acting",
                    "description": "Vauxhall telemetry for Gemini tool execution",
                }
            ],
        }
    ]
