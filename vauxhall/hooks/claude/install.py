# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Claude Code hooks."""

import sys
from pathlib import Path
from typing import Any

from vauxhall.hooks import common
from vauxhall.hooks.common import setup_venv

HOOK_MODULE = "vauxhall.hooks.claude.telemetry_hook"
HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "Stop",
    "SessionEnd",
)


def build_hook_command(venv_python: Path) -> str:
    """Build a platform-appropriate command for the Claude Code hook."""
    return common.build_hook_command(venv_python, HOOK_MODULE)


def load_settings(settings_path: Path) -> dict[str, Any]:
    """Back up, validate, and load existing Claude Code settings.

    Args:
        settings_path: Path to the Claude Code settings file.

    Returns:
        The existing valid settings, or an empty dictionary when absent.
    """
    return common.load_hook_settings(settings_path, "Claude Code")


def _is_vauxhall_handler(handler: object) -> bool:
    """Return whether a handler invokes Vauxhall's Claude Code hook module."""
    return common.is_hook_handler(handler, HOOK_MODULE)


def purge_vauxhall_hooks(settings: dict[str, Any]) -> None:
    """Remove previously installed Vauxhall Claude Code command handlers.

    Args:
        settings: Claude Code settings to modify.
    """
    common.purge_hook_handlers(settings, _is_vauxhall_handler)


def register_hook(settings: dict[str, Any], event: str, command: str) -> None:
    """Register the Vauxhall command handler for one Claude Code event.

    Args:
        settings: Claude Code settings to modify.
        event: Claude Code hook event name.
        command: Shell command Claude Code should execute.
    """
    handler = {"type": "command", "command": command, "timeout": 3}
    common.register_hook_handler(settings, event, handler)


def install() -> None:
    """Install Vauxhall telemetry hooks into the current Claude Code project."""
    print("Vauxhall Claude Code Hook Installer")
    print("-----------------------------------")

    cwd = Path.cwd()
    venv_dir = cwd / ".vauxhall-venv"
    target_settings = cwd / ".claude" / "settings.local.json"
    try:
        settings = load_settings(target_settings)
    except (TypeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    venv_python = setup_venv(venv_dir)
    purge_vauxhall_hooks(settings)

    hook_command = build_hook_command(venv_python.absolute())
    for event in HOOK_EVENTS:
        register_hook(settings, event, hook_command)
        print(f"Registered hook for: {event}")

    try:
        common.write_json_atomically(target_settings, settings)
    except Exception as error:
        print(f"Error saving settings: {error}")
        sys.exit(1)

    print(f"\nSuccess! Hooks installed successfully in {target_settings}")
    print(f"Venv created at {venv_dir}")
    print("Restart Claude Code, or review the new hooks with /hooks.")


if __name__ == "__main__":
    install()
