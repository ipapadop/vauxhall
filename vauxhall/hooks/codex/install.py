# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Codex hooks."""

import sys
from pathlib import Path
from typing import Any

from vauxhall.hooks import common
from vauxhall.hooks.common import setup_venv

HOOK_MODULE = "vauxhall.hooks.codex.telemetry_hook"
HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "Stop",
    "Interrupt",
    "SessionEnd",
)


def build_hook_command(venv_python: Path) -> str:
    """Build a platform-appropriate command for the Codex hook."""
    return common.build_hook_command(venv_python, HOOK_MODULE)


def load_hooks(hooks_path: Path) -> dict[str, Any]:
    """Back up, validate, and load an existing Codex hooks configuration.

    Args:
        hooks_path: Path to the Codex hooks JSON file.

    Returns:
        The existing valid configuration, or an empty dictionary when absent.
    """
    return common.load_hook_settings(hooks_path, "Codex")


def _is_vauxhall_handler(handler: object) -> bool:
    """Return whether a handler invokes Vauxhall's Codex hook module."""
    return common.is_hook_handler(handler, HOOK_MODULE)


def purge_vauxhall_hooks(config: dict[str, Any]) -> None:
    """Remove previously installed Vauxhall Codex command handlers.

    Args:
        config: Codex hook configuration to modify.
    """
    common.purge_hook_handlers(config, _is_vauxhall_handler)


def register_hook(config: dict[str, Any], event: str, command: str) -> None:
    """Register the Vauxhall command handler for one Codex event.

    Args:
        config: Codex hook configuration to modify.
        event: Codex lifecycle event name.
        command: Shell command Codex should execute.
    """
    handler = {
        "type": "command",
        "command": command,
        "statusMessage": "Sending Vauxhall telemetry",
        "timeout": 3,
    }
    common.register_hook_handler(config, event, handler)


def install() -> None:
    """Install Vauxhall telemetry hooks into the current Codex project."""
    print("Vauxhall Codex Hook Installer")
    print("-----------------------------")

    cwd = Path.cwd()
    venv_dir = cwd / ".vauxhall-venv"
    target_hooks = cwd / ".codex" / "hooks.json"
    try:
        config = load_hooks(target_hooks)
    except (TypeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    venv_python = setup_venv(venv_dir)
    config.setdefault("description", "Vauxhall telemetry hooks for Codex.")
    purge_vauxhall_hooks(config)

    hook_command = build_hook_command(venv_python.absolute())
    for event in HOOK_EVENTS:
        register_hook(config, event, hook_command)
        print(f"Registered hook for: {event}")

    try:
        common.write_json_atomically(target_hooks, config)
    except Exception as error:
        print(f"Error saving hooks: {error}")
        sys.exit(1)

    print(f"\nSuccess! Hooks installed successfully in {target_hooks}")
    print(f"Venv created at {venv_dir}")
    print("Review and trust the hooks with /hooks in Codex.")


if __name__ == "__main__":
    install()
