# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Helpers shared by the built-in agent hook installers."""

import base64
import importlib.metadata
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from vauxhall import __version__
from vauxhall.core.config_store import write_json_atomically

WINDOWS_ENCODED_COMMAND_PREFIX = (
    "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
)


@dataclass(frozen=True)
class HookInstaller:
    """How one agent's Vauxhall hook handlers are written into a workspace.

    Attributes:
        agent: Agent name shown in messages.
        module: Hook module the generated commands run.
        settings_path: Settings file holding the agent's hooks, relative to the
            workspace.
        handlers: Handler fields, other than type and command, for each event.
        next_step: Message printed after a successful installation.
        is_owned: Predicate for previously installed handlers to replace;
            defaults to generated commands that run ``module``.
        option_keys: Keys under ``hooks`` that hold options rather than events.
        defaults: Top-level settings to add when absent.
    """

    agent: str
    module: str
    settings_path: Path
    handlers: Mapping[str, Mapping[str, Any]]
    next_step: str
    is_owned: Callable[[object], bool] | None = None
    option_keys: frozenset[str] = frozenset()
    defaults: Mapping[str, Any] | None = None

    def owns(self, handler: object) -> bool:
        """Return whether a handler is one this installer should replace.

        Args:
            handler: The handler entry from the agent's settings file.

        Returns:
            Whether a previous run of this installer wrote the handler.
        """
        if self.is_owned is not None:
            return self.is_owned(handler)
        return is_hook_handler(handler, self.module)


def is_hook_handler(handler: object, module: str) -> bool:
    """Return whether a handler is a generated command that runs a hook module.

    Args:
        handler: The handler entry from an agent's settings file.
        module: The hook module the command is expected to run.

    Returns:
        Whether the handler runs that module, including the Windows
        base64-encoded command form.
    """
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
    """Return whether a shell command has a generated hook invocation shape.

    Args:
        command: The shell command to inspect.
        module: The hook module the command is expected to run.

    Returns:
        Whether the command is a Python interpreter running that module.
    """
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
    """Validate the nested settings structures modified by an installer.

    Args:
        settings: The parsed settings file.
        agent: Agent name used in error messages.
        option_keys: Keys under ``hooks`` that hold options rather than events.

    Raises:
        TypeError: If the settings, its ``hooks`` mapping, or any event's
            matcher groups and handlers are not the expected shape.
    """
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

    Raises:
        OSError: If the settings directory cannot be created, or the existing
            file cannot be copied to its backup. The backup is made before the
            file is read, so an unreadable file fails here.
        ValueError: If the backed-up file cannot be read or parsed.
        TypeError: If the existing settings have an unexpected shape.
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
    """Remove owned handlers and the groups and events they leave empty.

    Args:
        settings: The settings to purge, modified in place.
        is_owned: Predicate naming the handlers this installer wrote.
        option_keys: Keys under ``hooks`` that hold options rather than events.
    """
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
    """Append a handler to the event's catch-all matcher group.

    Args:
        settings: The settings to register into, modified in place.
        event: The hook event the handler runs on.
        handler: The handler to append.
    """
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    for group in groups:
        if group.get("matcher") == "*":
            group.setdefault("hooks", []).append(handler)
            return
    groups.append({"matcher": "*", "hooks": [handler]})


def build_hook_command(venv_python: Path, module: str) -> str:
    """Build a platform-appropriate command that runs a hook module.

    Args:
        venv_python: Python executable of the hooks environment.
        module: The hook module to run.

    Returns:
        The command to store in the agent's settings file, base64-encoded for
        PowerShell on Windows.
    """
    if os.name == "nt":
        python_path = str(venv_python).replace("'", "''")
        script = f"& '{python_path}' -m {module}"
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode()
        return f"{WINDOWS_ENCODED_COMMAND_PREFIX}{encoded_script}"
    return shlex.join([str(venv_python), "-m", module])


def _hooks_requirement() -> str:
    """Return a pip requirement for the Vauxhall source running this installer.

    pip records where a distribution came from (PEP 610) when it is installed
    from a Git repository, a local directory, or an archive, so hook
    environments install from that same source. Other installations use the
    matching release from the package index.

    Returns:
        A pip requirement specifier for the hooks extra.
    """
    try:
        recorded = importlib.metadata.distribution("vauxhall").read_text(
            "direct_url.json"
        )
        direct_url = json.loads(recorded or "null")
    except (importlib.metadata.PackageNotFoundError, ValueError):
        direct_url = None
    if not isinstance(direct_url, dict) or not isinstance(direct_url.get("url"), str):
        return f"vauxhall[hooks]=={__version__}"

    url = direct_url["url"]
    vcs_info = direct_url.get("vcs_info")
    if isinstance(vcs_info, dict):
        url = f"{vcs_info.get('vcs', 'git')}+{url}"
        commit_id = vcs_info.get("commit_id")
        if isinstance(commit_id, str) and commit_id:
            url = f"{url}@{commit_id}"
    subdirectory = direct_url.get("subdirectory")
    if isinstance(subdirectory, str) and subdirectory:
        url = f"{url}#subdirectory={subdirectory}"
    if isinstance(vcs_info, dict) and not urlsplit(direct_url["url"]).netloc:
        # Requirement URLs need a host, so pip gets a local Git repository as a
        # bare URL; the hooks extra adds no dependencies.
        return url
    return f"vauxhall[hooks] @ {url}"


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

    requirement = _hooks_requirement()
    print(f"Installing {requirement}...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", requirement],
        check=True,
        capture_output=True,
    )
    return venv_python


def _register_hooks(
    installer: HookInstaller, settings: dict[str, Any], venv_python: Path
) -> None:
    """Replace an installer's handlers in already-loaded settings.

    Args:
        installer: The agent installer whose handlers are registered.
        settings: The agent's settings, modified in place.
        venv_python: Python executable of the hooks environment.
    """
    for key, value in (installer.defaults or {}).items():
        settings.setdefault(key, value)
    purge_hook_handlers(settings, installer.owns, installer.option_keys)

    command = build_hook_command(venv_python.absolute(), installer.module)
    for event, fields in installer.handlers.items():
        handler = {"type": "command", "command": command, **fields}
        register_hook_handler(settings, event, handler)
        print(f"Registered {installer.agent} hook for: {event}")


def install_hooks(installers: Sequence[HookInstaller]) -> None:
    """Install one or more agents' Vauxhall hook handlers from this directory.

    Every agent shares one hooks environment, so it is built once no matter how
    many agents are installed. Existing settings are loaded and validated for
    all of them before any environment setup, so an invalid file leaves every
    settings file unchanged. Each settings file is then replaced atomically.

    Args:
        installers: The agents to install, in the order they are written.
    """
    agents = ", ".join(installer.agent for installer in installers)
    title = f"Vauxhall Hook Installer: {agents}"
    print(title)
    print("-" * len(title))

    workspace = Path.cwd()
    venv_dir = workspace / ".vauxhall-venv"
    loaded = []
    for installer in installers:
        settings_path = workspace / installer.settings_path
        try:
            settings = load_hook_settings(
                settings_path, installer.agent, installer.option_keys
            )
        except (TypeError, ValueError) as error:
            print(f"Error: {error}")
            sys.exit(1)
        loaded.append((installer, settings_path, settings))

    venv_python = setup_venv(venv_dir)
    for installer, settings_path, settings in loaded:
        _register_hooks(installer, settings, venv_python)
        try:
            write_json_atomically(settings_path, settings)
        except Exception as error:
            print(f"Error saving {installer.agent} settings: {error}")
            sys.exit(1)
        print(f"Success! {installer.agent} hooks installed in {settings_path}")

    print(f"\nVenv created at {venv_dir}")
    for installer in installers:
        print(installer.next_step)
