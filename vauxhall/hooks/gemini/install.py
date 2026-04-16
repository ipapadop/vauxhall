# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Gemini CLI hooks."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def install():
    print("Vauxhall Gemini Hook Installer")
    print("------------------------------")

    # 1. Paths and Environment Setup
    cwd = Path.cwd()
    install_script_dir = Path(__file__).parent.absolute()
    hook_script = install_script_dir / "telemetry_hook.py"
    repo_root = install_script_dir.parents[2]

    venv_dir = cwd / ".vauxhall-venv"

    if not hook_script.exists():
        print(f"Error: Could not find hook script at {hook_script}")
        sys.exit(1)

    # 2. Create Virtual Environment
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

    # 3. Install Dependencies
    print("Installing dependencies into venv...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "paho-mqtt", "PyYAML"],
        check=True,
        capture_output=True,
    )
    # Install the vauxhall package in editable mode from the absolute repo path
    print(f"Installing vauxhall package from {repo_root}...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-e", str(repo_root)],
        check=True,
        capture_output=True,
    )

    # 4. Locate Gemini settings
    target_settings = cwd / ".gemini" / "settings.json"
    if not target_settings.parent.exists():
        print(f"Creating directory: {target_settings.parent}")
        target_settings.parent.mkdir(parents=True, exist_ok=True)

    # 5. Load current settings
    settings = {}
    if target_settings.exists():
        print(f"Reading existing settings from {target_settings}")
        try:
            with open(target_settings, "r") as f:
                settings = json.load(f)
            # Create backup
            backup_path = target_settings.with_suffix(".json.bak")
            shutil.copy(target_settings, backup_path)
            print(f"Backup created at {backup_path}")
        except Exception as e:
            print(f"Warning: Could not read existing settings: {e}")

    # 6. Prepare hook definitions
    if "hooks" not in settings:
        settings["hooks"] = {}

    # Purge old vauxhall hooks
    print("Purging old Vauxhall hooks...")
    for event in settings["hooks"]:
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

    hook_command = f"{venv_python.absolute()} {hook_script.absolute()}"

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

    # 7. Inject hooks for all events
    for event, config in hook_configs.items():
        if event not in settings["hooks"]:
            settings["hooks"][event] = []

        new_hook = {
            "name": config["name"],
            "type": "command",
            "command": hook_command,
            "description": config["description"],
        }

        # Check if a hook with this name already exists in any matcher group
        installed = False
        for matcher_group in settings["hooks"][event]:
            if matcher_group.get("matcher") == "*":
                hooks_list = matcher_group.get("hooks", [])
                for i, existing_hook in enumerate(hooks_list):
                    if existing_hook.get("name") == config["name"]:
                        hooks_list[i] = new_hook
                        installed = True
                        break
                if not installed:
                    hooks_list.append(new_hook)
                    installed = True
                break

        if not installed:
            settings["hooks"][event].append({"matcher": "*", "hooks": [new_hook]})
        print(f"Registered hook for: {event}")

    # 8. Save settings
    try:
        with open(target_settings, "w") as f:
            json.dump(settings, f, indent=2)
        print(f"\nSuccess! Hooks installed successfully in {target_settings}")
        print(f"Venv created at {venv_dir}")
        print("You can now monitor this workspace in the Vauxhall Dashboard.")
    except Exception as e:
        print(f"Error saving settings: {e}")
        sys.exit(1)


if __name__ == "__main__":
    install()
