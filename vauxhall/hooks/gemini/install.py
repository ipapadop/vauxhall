# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Gemini CLI hooks."""

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from vauxhall import __version__

HOOK_MODULE = "vauxhall.hooks.gemini.telemetry_hook"


def build_hook_command(venv_python: Path) -> str:
    """Build a platform-appropriate command for the Gemini hook."""
    arguments = [str(venv_python), "-m", HOOK_MODULE]
    if os.name == "nt":
        python_path = str(venv_python).replace("'", "''")
        script = f"& '{python_path}' -m {HOOK_MODULE}"
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode()
        return (
            "powershell.exe -NoProfile -NonInteractive "
            f"-EncodedCommand {encoded_script}"
        )
    return shlex.join(arguments)


def setup_venv(venv_dir: Path) -> Path:
    """Create a virtual environment and install dependencies.

    Args:
        venv_dir: Path to the virtual environment directory.

    Returns:
        Path: The path to the venv's Python executable.
    """
    if venv_dir.exists():
        print(f"Removing existing venv at {venv_dir}...")
        shutil.rmtree(venv_dir)

    print(f"Creating virtual environment in {venv_dir}...")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    # Detect venv python executable
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    requirement = f"vauxhall[hooks]=={__version__}"
    print(f"Installing {requirement}...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", requirement],
        check=True,
        capture_output=True,
    )
    return venv_python


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
    for event in list(settings["hooks"].keys()):
        for matcher_group in settings["hooks"][event]:
            if "hooks" in matcher_group:
                matcher_group["hooks"] = [
                    h
                    for h in matcher_group["hooks"]
                    if not h.get("name", "").startswith("vauxhall-")
                ]
        # Remove groups that are now empty
        settings["hooks"][event] = [
            mg for mg in settings["hooks"][event] if mg.get("hooks")
        ]


def register_hook(settings: dict, event: str, hook_config: dict, command: str) -> None:
    """Register a single hook in the settings dictionary.

    Args:
        settings: The settings dictionary to modify.
        event: The hook event name (e.g., BeforeAgent).
        hook_config: Dictionary with hook name and description.
        command: The command to execute for the hook.
    """
    if "hooks" not in settings:
        settings["hooks"] = {}

    if event not in settings["hooks"]:
        settings["hooks"][event] = []

    new_hook = {
        "name": hook_config["name"],
        "type": "command",
        "command": command,
        "description": hook_config["description"],
    }

    installed = False
    for matcher_group in settings["hooks"][event]:
        if matcher_group.get("matcher") == "*":
            hooks_list = matcher_group.setdefault("hooks", [])
            for i, existing_hook in enumerate(hooks_list):
                if existing_hook.get("name") == hook_config["name"]:
                    hooks_list[i] = new_hook
                    installed = True
                    break
            if not installed:
                hooks_list.append(new_hook)
                installed = True
            break

    if not installed:
        settings["hooks"][event].append({"matcher": "*", "hooks": [new_hook]})


def install() -> None:
    """Main installation entry point."""
    print("Vauxhall Gemini Hook Installer")
    print("------------------------------")

    # 1. Paths and Environment Setup
    cwd = Path.cwd()
    venv_dir = cwd / ".vauxhall-venv"

    # 2. Setup Venv
    venv_python = setup_venv(venv_dir)

    # 3. Load settings
    target_settings = cwd / ".gemini" / "settings.json"
    settings = load_settings(target_settings)

    # 4. Prepare hooks
    purge_vauxhall_hooks(settings)

    hook_command = build_hook_command(venv_python.absolute())
    hook_configs = {
        "BeforeAgent": {
            "name": "vauxhall-thinking",
            "description": "Vauxhall telemetry for Gemini thinking state",
        },
        "AfterAgent": {
            "name": "vauxhall-idle",
            "description": "Vauxhall telemetry for Gemini idle state",
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

    # 5. Register hooks
    for event, config in hook_configs.items():
        register_hook(settings, event, config, hook_command)
        print(f"Registered hook for: {event}")

    # 6. Save settings
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
