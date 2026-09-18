# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Installation utility for Vauxhall Claude Code hooks."""

from pathlib import Path

from vauxhall.hooks import installation

HOOK_MODULE = "vauxhall.hooks.claude.telemetry_hook"
# The hook command contains a machine-specific path, so it belongs in local settings.
SETTINGS_PATH = Path(".claude") / "settings.local.json"
HANDLERS = {
    event: {"timeout": 3}
    for event in (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PostToolUseFailure",
        "Notification",
        "MessageDisplay",
        "SubagentStart",
        "PreCompact",
        "PostCompact",
        "Stop",
        "StopFailure",
        "SessionEnd",
    )
}


def install() -> None:
    """Install Vauxhall telemetry hooks into the current Claude Code project."""
    installation.install_hooks(
        agent="Claude Code",
        module=HOOK_MODULE,
        settings_path=Path.cwd() / SETTINGS_PATH,
        handlers=HANDLERS,
        next_step="Restart Claude Code, or review the new hooks with /hooks.",
    )


if __name__ == "__main__":
    install()
