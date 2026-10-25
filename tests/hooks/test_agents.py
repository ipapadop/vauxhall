# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the agent installer map and workspace agent detection."""

from vauxhall.hooks import agents
from vauxhall.hooks.claude import install as claude
from vauxhall.hooks.codex import install as codex
from vauxhall.hooks.gemini import install as gemini


def test_installers_name_every_agent() -> None:
    """The map names each built-in agent's installer, in CLI order."""
    assert list(agents.INSTALLERS) == ["claude", "codex", "gemini"]
    assert agents.INSTALLERS["claude"] is claude.INSTALLER
    assert agents.INSTALLERS["codex"] is codex.INSTALLER
    assert agents.INSTALLERS["gemini"] is gemini.INSTALLER
