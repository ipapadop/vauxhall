# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""The agents Vauxhall installs hooks for, and which of them a workspace uses."""

import json
import os
from pathlib import Path

from vauxhall.hooks.claude import telemetry_hook as claude_hook
from vauxhall.hooks.codex import telemetry_hook as codex_hook
from vauxhall.hooks.gemini import telemetry_hook as gemini_hook
from vauxhall.hooks.installation import HookInstaller, validate_hook_settings

_GEMINI_HANDLERS = {
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
    "SessionStart": {
        "name": "vauxhall-session-start",
        "description": "Vauxhall telemetry for Gemini session start",
    },
    "PreCompress": {
        "name": "vauxhall-compress",
        "description": "Vauxhall telemetry for Gemini context compression",
    },
}

INSTALLERS: dict[str, HookInstaller] = {
    "claude": HookInstaller(
        agent="Claude Code",
        module=claude_hook.__name__,
        settings_path=Path(".claude") / "settings.local.json",
        handlers={event: {"timeout": 3} for event in claude_hook.HANDLERS},
        next_step="Restart Claude Code, or review the new hooks with /hooks.",
    ),
    "codex": HookInstaller(
        agent="Codex",
        module=codex_hook.__name__,
        settings_path=Path(".codex") / "hooks.json",
        handlers={
            event: {"statusMessage": "Sending Vauxhall telemetry", "timeout": 3}
            for event in codex_hook.HANDLERS
        },
        defaults={"description": "Vauxhall telemetry hooks for Codex."},
        next_step="Review and trust the hooks with /hooks in Codex.",
    ),
    "gemini": HookInstaller(
        agent="Gemini",
        module=gemini_hook.__name__,
        settings_path=Path(".gemini") / "settings.json",
        handlers=_GEMINI_HANDLERS,
        # Hook-system options that older Gemini CLI releases keep beside events.
        option_keys=frozenset({"enabled", "disabled", "notifications"}),
        next_step="You can now monitor this workspace in the Vauxhall Dashboard.",
    ),
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
