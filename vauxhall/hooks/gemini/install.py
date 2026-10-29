# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Gemini CLI hooks."""

from pathlib import Path

from vauxhall.hooks import installation

HOOK_MODULE = "vauxhall.hooks.gemini.telemetry_hook"
SETTINGS_PATH = Path(".gemini") / "settings.json"
HANDLERS = {
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
# Hook-system options that older Gemini CLI releases keep beside event entries.
_HOOK_OPTION_KEYS = frozenset({"enabled", "disabled", "notifications"})

INSTALLER = installation.HookInstaller(
    agent="Gemini",
    module=HOOK_MODULE,
    settings_path=SETTINGS_PATH,
    handlers=HANDLERS,
    option_keys=_HOOK_OPTION_KEYS,
    next_step="You can now monitor this workspace in the Vauxhall Dashboard.",
)
