# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Codex hooks."""

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def _validate_hook_config(config: dict[str, Any]) -> None:
    """Validate the nested structures modified by the installer."""
    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        msg = "Codex hooks must be a JSON object"
        raise TypeError(msg)
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            msg = f"Codex hook event {event!r} must contain a JSON array"
            raise TypeError(msg)
        for group in groups:
            if not isinstance(group, dict):
                msg = f"Codex hook event {event!r} contains a non-object group"
                raise TypeError(msg)
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                msg = f"Codex hook event {event!r} group must contain a hooks array"
                raise TypeError(msg)
            if not all(isinstance(handler, dict) for handler in handlers):
                msg = f"Codex hook event {event!r} contains a non-object handler"
                raise TypeError(msg)


def build_hook_command(venv_python: Path) -> str:
    """Build a platform-appropriate command for the Codex hook."""
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


def setup_venv(venv_dir: Path, repo_root: Path) -> Path:
    """Create an isolated environment containing the Vauxhall hooks package.

    Args:
        venv_dir: Destination for the virtual environment.
        repo_root: Root of the Vauxhall source repository.

    Returns:
        Path to the environment's Python executable.
    """
    if venv_dir.exists():
        print(f"Removing existing venv at {venv_dir}...")
        shutil.rmtree(venv_dir)

    print(f"Creating virtual environment in {venv_dir}...")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    print("Installing dependencies into venv...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
    )
    print(f"Installing vauxhall[hooks] from {repo_root}...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-e", f"{repo_root}[hooks]"],
        check=True,
        capture_output=True,
    )
    return venv_python


def load_hooks(hooks_path: Path) -> dict[str, Any]:
    """Back up, validate, and load an existing Codex hooks configuration.

    Args:
        hooks_path: Path to the Codex hooks JSON file.

    Returns:
        The existing valid configuration, or an empty dictionary when absent.
    """
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    if not hooks_path.exists():
        return {}

    print(f"Reading existing hooks from {hooks_path}")
    backup_path = hooks_path.with_suffix(".json.bak")
    shutil.copy(hooks_path, backup_path)
    print(f"Backup created at {backup_path}")
    try:
        with hooks_path.open() as file:
            hooks = json.load(file)
    except Exception as error:
        msg = f"Could not read existing hooks: {error}"
        raise ValueError(msg) from error
    if not isinstance(hooks, dict):
        msg = "Codex hooks configuration must be a JSON object"
        raise TypeError(msg)
    _validate_hook_config(hooks)
    return hooks


def purge_vauxhall_hooks(config: dict[str, Any]) -> None:
    """Remove previously installed Vauxhall Codex command handlers.

    Args:
        config: Codex hook configuration to modify.
    """
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return

    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            group["hooks"] = [
                handler
                for handler in group["hooks"]
                if not (
                    isinstance(handler, dict)
                    and HOOK_MODULE in str(handler.get("command", ""))
                )
            ]
        hooks[event] = [
            group for group in groups if isinstance(group, dict) and group.get("hooks")
        ]
        if not hooks[event]:
            del hooks[event]


def register_hook(config: dict[str, Any], event: str, command: str) -> None:
    """Register the Vauxhall command handler for one Codex event.

    Args:
        config: Codex hook configuration to modify.
        event: Codex lifecycle event name.
        command: Shell command Codex should execute.
    """
    hooks = config.setdefault("hooks", {})
    groups = hooks.setdefault(event, [])
    handler = {
        "type": "command",
        "command": command,
        "statusMessage": "Sending Vauxhall telemetry",
        "timeout": 3,
    }
    for group in groups:
        if group.get("matcher") == "*":
            group.setdefault("hooks", []).append(handler)
            return
    groups.append({"matcher": "*", "hooks": [handler]})


def install() -> None:
    """Install Vauxhall telemetry hooks into the current Codex project."""
    print("Vauxhall Codex Hook Installer")
    print("-----------------------------")

    cwd = Path.cwd()
    install_script_dir = Path(__file__).parent.absolute()
    repo_root = install_script_dir.parents[2]
    venv_dir = cwd / ".vauxhall-venv"
    target_hooks = cwd / ".codex" / "hooks.json"
    try:
        config = load_hooks(target_hooks)
    except (TypeError, ValueError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    venv_python = setup_venv(venv_dir, repo_root)
    config.setdefault("description", "Vauxhall telemetry hooks for Codex.")
    purge_vauxhall_hooks(config)

    hook_command = build_hook_command(venv_python.absolute())
    for event in HOOK_EVENTS:
        register_hook(config, event, hook_command)
        print(f"Registered hook for: {event}")

    try:
        with target_hooks.open("w") as file:
            json.dump(config, file, indent=2)
            file.write("\n")
    except Exception as error:
        print(f"Error saving hooks: {error}")
        sys.exit(1)

    print(f"\nSuccess! Hooks installed successfully in {target_hooks}")
    print(f"Venv created at {venv_dir}")
    print("Review and trust the hooks with /hooks in Codex.")


if __name__ == "__main__":
    install()
