# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the Vauxhall hook installer."""

from pathlib import Path

from vauxhall.hooks.gemini.install import (
    load_settings,
    purge_vauxhall_hooks,
    register_hook,
)


def test_load_settings(tmp_path: Path) -> None:
    """Verify load_settings creates backup and returns dict."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"existing": "value"}')

    settings = load_settings(settings_file)
    assert settings == {"existing": "value"}
    assert (tmp_path / "settings.json.bak").exists()


def test_load_settings_empty(tmp_path: Path) -> None:
    """Verify load_settings returns empty dict if file is missing."""
    settings_file = tmp_path / "settings.json"
    settings = load_settings(settings_file)
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
    purge_vauxhall_hooks(settings)
    assert len(settings["hooks"]["BeforeAgent"][0]["hooks"]) == 1
    assert settings["hooks"]["BeforeAgent"][0]["hooks"][0]["name"] == "user-custom-hook"


def test_register_hook() -> None:
    """Verify register_hook appends or updates correctly."""
    settings = {}
    config = {"name": "vauxhall-test", "description": "Test hook"}
    command = "python test.py"

    register_hook(settings, "AfterAgent", config, command)

    assert "AfterAgent" in settings["hooks"]
    assert settings["hooks"]["AfterAgent"][0]["matcher"] == "*"

    hook = settings["hooks"]["AfterAgent"][0]["hooks"][0]
    assert hook["name"] == "vauxhall-test"
    assert hook["command"] == command
