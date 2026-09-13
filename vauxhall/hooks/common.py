# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Helpers shared by the built-in Codex and Gemini hooks and installers."""

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from uuid import uuid4

from vauxhall import __version__
from vauxhall.core.config import ConfigurationError

WINDOWS_ENCODED_COMMAND_PREFIX = (
    "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
)
_CANCELLATION_MARKERS = frozenset({"cancelled", "canceled", "aborted"})


def is_cancelled(response: dict[str, Any]) -> bool:
    """Return whether a tool response contains a cancellation marker."""
    if response.get("cancelled") is True or response.get("canceled") is True:
        return True
    candidates = [response.get(key) for key in ("code", "status", "name")]
    error = response.get("error")
    if isinstance(error, dict):
        candidates.extend(error.get(key) for key in ("code", "status", "name"))
    return any(
        isinstance(value, str) and value.lower() in _CANCELLATION_MARKERS
        for value in candidates
    )


def run_hook(send_telemetry: Callable[[dict[str, Any]], None]) -> None:
    """Process one hook event from stdin without disrupting the hook protocol."""
    try:
        with redirect_stdout(sys.stderr):
            from vauxhall.core.logging import setup_logging  # noqa: PLC0415
            from vauxhall.hooks.config import hook_settings  # noqa: PLC0415

            setup_logging(level=hook_settings.logging.level)
            input_data = json.load(sys.stdin)
            if isinstance(input_data, dict):
                send_telemetry(input_data)
    except ConfigurationError as error:
        print(error, file=sys.stderr)
    except Exception:
        pass
    print("{}")


def is_hook_handler(handler: object, module: str) -> bool:
    """Return whether a handler is a generated command that runs a hook module."""
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False
    command = handler.get("command")
    if not isinstance(command, str):
        return False
    if _is_hook_invocation(command, module):
        return True
    if not command.startswith(WINDOWS_ENCODED_COMMAND_PREFIX):
        return False
    encoded_script = command.removeprefix(WINDOWS_ENCODED_COMMAND_PREFIX)
    try:
        script = base64.b64decode(encoded_script, validate=True).decode("utf-16-le")
    except (UnicodeError, ValueError):
        return False
    return _is_hook_invocation(script, module)


def _is_hook_invocation(command: str, module: str) -> bool:
    """Return whether a shell command has a generated hook invocation shape."""
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    if len(arguments) == 3:
        executable = arguments[0]
    elif len(arguments) == 4 and arguments[0] == "&":
        executable = arguments[1]
    else:
        return False
    executable_name = executable.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    is_python = executable_name.casefold() in {"python", "python.exe"}
    return is_python and arguments[-2:] == ["-m", module]


def _validate_hook_settings(
    settings: object, agent: str, option_keys: frozenset[str]
) -> None:
    """Validate the nested settings structures modified by an installer."""
    if not isinstance(settings, dict):
        msg = f"{agent} settings must be a JSON object"
        raise TypeError(msg)
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        msg = f"{agent} hooks must be a JSON object"
        raise TypeError(msg)
    for event, groups in hooks.items():
        if event in option_keys:
            continue
        if not isinstance(groups, list):
            msg = f"{agent} hook event {event!r} must contain a JSON array"
            raise TypeError(msg)
        for group in groups:
            if not isinstance(group, dict):
                msg = f"{agent} hook event {event!r} contains a non-object group"
                raise TypeError(msg)
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                msg = f"{agent} hook event {event!r} group must contain a hooks array"
                raise TypeError(msg)
            if not all(isinstance(handler, dict) for handler in handlers):
                msg = f"{agent} hook event {event!r} contains a non-object handler"
                raise TypeError(msg)


def load_hook_settings(
    path: Path, agent: str, option_keys: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Back up, validate, and load an existing hook settings file.

    Args:
        path: Path to the agent's JSON settings file.
        agent: Agent name used in error messages.
        option_keys: Keys under ``hooks`` that hold options rather than events.

    Returns:
        The existing valid settings, or an empty dictionary when absent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {}

    print(f"Reading existing settings from {path}")
    backup_path = path.with_suffix(".json.bak")
    shutil.copy(path, backup_path)
    print(f"Backup created at {backup_path}")
    try:
        with path.open() as file:
            settings = json.load(file)
    except Exception as error:
        msg = f"Could not read existing settings: {error}"
        raise ValueError(msg) from error
    _validate_hook_settings(settings, agent, option_keys)
    return settings


def purge_hook_handlers(
    settings: dict[str, Any],
    is_owned: Callable[[object], bool],
    option_keys: frozenset[str] = frozenset(),
) -> None:
    """Remove owned handlers and the groups and events they leave empty."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return

    for event in list(hooks):
        groups = hooks[event]
        if event in option_keys or not isinstance(groups, list):
            continue
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                group["hooks"] = [
                    handler for handler in group["hooks"] if not is_owned(handler)
                ]
        hooks[event] = [
            group for group in groups if isinstance(group, dict) and group.get("hooks")
        ]
        if not hooks[event]:
            del hooks[event]


def register_hook_handler(
    settings: dict[str, Any], event: str, handler: dict[str, Any]
) -> None:
    """Append a handler to the event's catch-all matcher group."""
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    for group in groups:
        if group.get("matcher") == "*":
            group.setdefault("hooks", []).append(handler)
            return
    groups.append({"matcher": "*", "hooks": [handler]})


def write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    """Replace a JSON file so readers see either the old or the new content."""
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("x") as file:
            json.dump(data, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            shutil.copymode(path, temporary_path)
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def build_hook_command(venv_python: Path, module: str) -> str:
    """Build a platform-appropriate command that runs a hook module."""
    if os.name == "nt":
        python_path = str(venv_python).replace("'", "''")
        script = f"& '{python_path}' -m {module}"
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode()
        return f"{WINDOWS_ENCODED_COMMAND_PREFIX}{encoded_script}"
    return shlex.join([str(venv_python), "-m", module])


def setup_venv(venv_dir: Path) -> Path:
    """Create an isolated environment containing the Vauxhall hooks package.

    Args:
        venv_dir: Destination for the virtual environment.

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

    requirement = f"vauxhall[hooks]=={__version__}"
    print(f"Installing {requirement}...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", requirement],
        check=True,
        capture_output=True,
    )
    return venv_python
