# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Codex hooks."""

from pathlib import Path

from vauxhall.hooks import installation

HOOK_MODULE = "vauxhall.hooks.codex.telemetry_hook"
SETTINGS_PATH = Path(".codex") / "hooks.json"
HANDLERS = {
    event: {"statusMessage": "Sending Vauxhall telemetry", "timeout": 3}
    for event in (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "SubagentStart",
        "PreCompact",
        "PostCompact",
        "Stop",
        "Interrupt",
        "SessionEnd",
    )
}


def install() -> None:
    """Install Vauxhall telemetry hooks into the current Codex project."""
    installation.install_hooks(
        agent="Codex",
        module=HOOK_MODULE,
        settings_path=Path.cwd() / SETTINGS_PATH,
        handlers=HANDLERS,
        defaults={"description": "Vauxhall telemetry hooks for Codex."},
        next_step="Review and trust the hooks with /hooks in Codex.",
    )


if __name__ == "__main__":
    install()
