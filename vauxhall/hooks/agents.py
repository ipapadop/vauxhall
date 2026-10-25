# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""The agents Vauxhall installs hooks for."""

from vauxhall.hooks.claude import install as claude
from vauxhall.hooks.codex import install as codex
from vauxhall.hooks.gemini import install as gemini
from vauxhall.hooks.installation import HookInstaller

INSTALLERS: dict[str, HookInstaller] = {
    "claude": claude.INSTALLER,
    "codex": codex.INSTALLER,
    "gemini": gemini.INSTALLER,
}
