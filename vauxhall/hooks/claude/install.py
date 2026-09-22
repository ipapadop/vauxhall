# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Claude Code hooks."""

from pathlib import Path

from vauxhall.hooks import installation
from vauxhall.hooks.claude import telemetry_hook

HOOK_MODULE = "vauxhall.hooks.claude.telemetry_hook"
# The hook command contains a machine-specific path, so it belongs in local settings.
SETTINGS_PATH = Path(".claude") / "settings.local.json"
HANDLERS = {event: {"timeout": 3} for event in telemetry_hook._HANDLERS}

INSTALLER = installation.HookInstaller(
    agent="Claude Code",
    module=HOOK_MODULE,
    settings_path=SETTINGS_PATH,
    handlers=HANDLERS,
    next_step="Restart Claude Code, or review the new hooks with /hooks.",
)
