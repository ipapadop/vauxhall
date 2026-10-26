# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""The agents Vauxhall installs hooks for, and which of them a workspace uses."""

import json
import os
from pathlib import Path

from vauxhall.hooks.claude import install as claude
from vauxhall.hooks.codex import install as codex
from vauxhall.hooks.gemini import install as gemini
from vauxhall.hooks.installation import HookInstaller, validate_hook_settings

INSTALLERS: dict[str, HookInstaller] = {
    "claude": claude.INSTALLER,
    "codex": codex.INSTALLER,
    "gemini": gemini.INSTALLER,
}


def detect_agents(workspace: Path) -> list[dict[str, object]]:
    """Report which agents a workspace uses and which have Vauxhall hooks.

    Only reads: unlike installation, it creates no directory and no backup.

    Args:
        workspace: The workspace directory.

    Returns:
        One entry per agent in ``INSTALLERS`` order, with ``agent`` (its
        key), ``name``, ``detected`` (its config directory exists),
        ``installed`` (its settings hold a handler the installer owns), and
        ``error`` (why its settings couldn't be read, or ``None``).
    """
    return [
        _detect(workspace, agent, installer) for agent, installer in INSTALLERS.items()
    ]


def _detect(workspace: Path, agent: str, installer: HookInstaller) -> dict[str, object]:
    """Detect one agent in a workspace.

    Args:
        workspace: The workspace directory.
        agent: The agent's key in ``INSTALLERS``.
        installer: The agent's installer.

    Returns:
        The agent's entry, as described in ``detect_agents``.
    """
    entry: dict[str, object] = {
        "agent": agent,
        "name": installer.agent,
        # Unlike Path.is_dir before Python 3.14, it is False on a PermissionError.
        "detected": os.path.isdir(workspace / installer.settings_path.parts[0]),  # noqa: PTH112
        "installed": False,
        "error": None,
    }
    path = workspace / installer.settings_path
    try:
        # Reading, not Path.exists, which from Python 3.14 is False on a
        # PermissionError and would hide an unreadable workspace.
        settings = json.loads(path.read_text(encoding="utf-8"))
        validate_hook_settings(settings, installer.agent, installer.option_keys)
        entry["installed"] = _has_owned_handler(settings, installer)
    except (FileNotFoundError, NotADirectoryError):
        pass
    except (OSError, ValueError, TypeError) as error:
        entry["error"] = str(error)
    return entry


def _has_owned_handler(settings: dict, installer: HookInstaller) -> bool:
    """Return whether validated settings hold a handler the installer wrote.

    Args:
        settings: Settings that passed ``validate_hook_settings``.
        installer: The agent's installer.

    Returns:
        Whether any event's handler is owned by the installer.
    """
    return any(
        installer.owns(handler)
        for event, groups in settings.get("hooks", {}).items()
        if event not in installer.option_keys
        for group in groups
        for handler in group["hooks"]
    )
