# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Gemini CLI hooks."""

import json
import shutil
import sys
from pathlib import Path

from vauxhall.hooks import common
from vauxhall.hooks.common import setup_venv

HOOK_MODULE = "vauxhall.hooks.gemini.telemetry_hook"
HOOK_CONFIGS = {
    "BeforeAgent": {
        "name": "vauxhall-thinking",
        "description": "Vauxhall telemetry for Gemini thinking state",
    },
    "AfterAgent": {
        "name": "vauxhall-idle",
        "description": "Vauxhall telemetry for Gemini idle state",
    },
    "SessionEnd": {
        "name": "vauxhall-session-end",
        "description": "Vauxhall telemetry for Gemini session end",
    },
    "BeforeTool": {
        "name": "vauxhall-acting",
        "description": "Vauxhall telemetry for Gemini tool execution",
    },
    "AfterTool": {
        "name": "vauxhall-done",
        "description": "Vauxhall telemetry for Gemini tool completion",
    },
    "AfterModel": {
        "name": "vauxhall-model",
        "description": "Vauxhall telemetry for Gemini model completion",
    },
    "Notification": {
        "name": "vauxhall-waiting",
        "description": "Vauxhall telemetry for Gemini waiting for input",
    },
}


def build_hook_command(venv_python: Path) -> str:
    """Build a platform-appropriate command for the Gemini hook."""
    return common.build_hook_command(venv_python, HOOK_MODULE)


def load_settings(settings_path: Path) -> dict:
    """Load Gemini settings from a JSON file.

    Args:
        settings_path: Path to the settings.json file.

    Returns:
        dict: The loaded settings dictionary.
    """
    if not settings_path.parent.exists():
        print(f"Creating directory: {settings_path.parent}")
        settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        print(f"Reading existing settings from {settings_path}")
        try:
            with settings_path.open() as f:
                settings = json.load(f)
            # Create backup
            backup_path = settings_path.with_suffix(".json.bak")
            shutil.copy(settings_path, backup_path)
            print(f"Backup created at {backup_path}")
        except Exception as e:
            print(f"Warning: Could not read existing settings: {e}")
        else:
            return settings
    return {}


def purge_vauxhall_hooks(settings: dict) -> None:
    """Remove existing vauxhall hooks from settings.

    Args:
        settings: The settings dictionary to modify.
    """
    if "hooks" not in settings:
        return

    print("Purging old Vauxhall hooks...")
    hooks = settings["hooks"]
    for event, groups in hooks.items():
        for matcher_group in groups:
            if "hooks" in matcher_group:
                matcher_group["hooks"] = [
                    h
                    for h in matcher_group["hooks"]
                    if not h.get("name", "").startswith("vauxhall-")
                ]
        # Remove groups that are now empty
        hooks[event] = [mg for mg in groups if mg.get("hooks")]


def register_hook(settings: dict, event: str, hook_config: dict, command: str) -> None:
    """Register a single hook in the settings dictionary.

    Args:
        settings: The settings dictionary to modify.
        event: The hook event name (e.g., BeforeAgent).
        hook_config: Dictionary with hook name and description.
        command: The command to execute for the hook.
    """
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    new_hook = {
        "name": hook_config["name"],
        "type": "command",
        "command": command,
        "description": hook_config["description"],
    }

    for matcher_group in groups:
        if matcher_group.get("matcher") == "*":
            hooks_list = matcher_group.setdefault("hooks", [])
            for i, existing_hook in enumerate(hooks_list):
                if existing_hook.get("name") == hook_config["name"]:
                    hooks_list[i] = new_hook
                    return
            hooks_list.append(new_hook)
            return

    groups.append({"matcher": "*", "hooks": [new_hook]})


def install() -> None:
    """Install Vauxhall telemetry hooks into the current Gemini workspace."""
    print("Vauxhall Gemini Hook Installer")
    print("------------------------------")

    cwd = Path.cwd()
    venv_dir = cwd / ".vauxhall-venv"
    venv_python = setup_venv(venv_dir)

    target_settings = cwd / ".gemini" / "settings.json"
    settings = load_settings(target_settings)
    purge_vauxhall_hooks(settings)

    hook_command = build_hook_command(venv_python.absolute())
    for event, config in HOOK_CONFIGS.items():
        register_hook(settings, event, config, hook_command)
        print(f"Registered hook for: {event}")

    try:
        with target_settings.open("w") as f:
            json.dump(settings, f, indent=2)
        print(f"\nSuccess! Hooks installed successfully in {target_settings}")
        print(f"Venv created at {venv_dir}")
        print("You can now monitor this workspace in the Vauxhall Dashboard.")
    except Exception as e:
        print(f"Error saving settings: {e}")
        sys.exit(1)


if __name__ == "__main__":
    install()
