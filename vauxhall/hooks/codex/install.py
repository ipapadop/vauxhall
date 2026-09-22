# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Codex hooks."""

from pathlib import Path

from vauxhall.hooks import installation
from vauxhall.hooks.codex import telemetry_hook

HOOK_MODULE = "vauxhall.hooks.codex.telemetry_hook"
SETTINGS_PATH = Path(".codex") / "hooks.json"
HANDLERS = {
    event: {"statusMessage": "Sending Vauxhall telemetry", "timeout": 3}
    for event in telemetry_hook.HANDLERS
}

INSTALLER = installation.HookInstaller(
    agent="Codex",
    module=HOOK_MODULE,
    settings_path=SETTINGS_PATH,
    handlers=HANDLERS,
    defaults={"description": "Vauxhall telemetry hooks for Codex."},
    next_step="Review and trust the hooks with /hooks in Codex.",
)
