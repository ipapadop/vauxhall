# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the agent installer map and workspace agent detection."""

import json
from pathlib import Path

import pytest

from vauxhall.hooks import agents, installation
from vauxhall.hooks.claude import install as claude
from vauxhall.hooks.codex import install as codex
from vauxhall.hooks.gemini import install as gemini


def test_installers_name_every_agent() -> None:
    """The map names each built-in agent's installer, in CLI order."""
    assert list(agents.INSTALLERS) == ["claude", "codex", "gemini"]
    assert agents.INSTALLERS["claude"] is claude.INSTALLER
    assert agents.INSTALLERS["codex"] is codex.INSTALLER
    assert agents.INSTALLERS["gemini"] is gemini.INSTALLER


def _write_settings(workspace: Path, agent: str, settings: object) -> Path:
    """Write an agent's settings file in a workspace.

    Args:
        workspace: The workspace.
        agent: Key in ``agents.INSTALLERS``.
        settings: Settings to write as JSON.

    Returns:
        The settings file.
    """
    path = workspace / agents.INSTALLERS[agent].settings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings))
    return path


def _with_handler(handler: dict[str, object]) -> dict[str, object]:
    """Return settings holding one handler under one event.

    Args:
        handler: The handler.

    Returns:
        Settings in the shape every agent uses.
    """
    return {"hooks": {"SessionStart": [{"matcher": "*", "hooks": [handler]}]}}


def _by_agent(workspace: Path) -> dict[str, dict[str, object]]:
    """Return detection results keyed by agent.

    Args:
        workspace: The workspace to detect.

    Returns:
        Each agent's entry.
    """
    return {entry["agent"]: entry for entry in agents.detect_agents(workspace)}


def test_detect_agents_in_an_empty_directory(tmp_path: Path) -> None:
    """No agent directory means nothing detected, installed, or wrong."""
    assert agents.detect_agents(tmp_path) == [
        {
            "agent": "claude",
            "name": "Claude Code",
            "detected": False,
            "installed": False,
            "error": None,
        },
        {
            "agent": "codex",
            "name": "Codex",
            "detected": False,
            "installed": False,
            "error": None,
        },
        {
            "agent": "gemini",
            "name": "Gemini",
            "detected": False,
            "installed": False,
            "error": None,
        },
    ]


def test_detect_agents_finds_agent_directories(tmp_path: Path) -> None:
    """An agent's config directory marks it detected, without hooks."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".gemini").mkdir()

    found = _by_agent(tmp_path)

    assert {agent: entry["detected"] for agent, entry in found.items()} == {
        "claude": True,
        "codex": False,
        "gemini": True,
    }
    assert not any(entry["installed"] for entry in found.values())


@pytest.mark.parametrize("agent", ["claude", "codex", "gemini"])
def test_detect_agents_finds_installed_hooks(tmp_path: Path, agent: str) -> None:
    """A handler the installer owns marks the agent installed."""
    module = agents.INSTALLERS[agent].module
    command = installation.build_hook_command(Path("/venv/bin/python"), module)
    _write_settings(
        tmp_path, agent, _with_handler({"type": "command", "command": command})
    )

    entry = _by_agent(tmp_path)[agent]

    assert entry["detected"] is True
    assert entry["installed"] is True
    assert entry["error"] is None


def test_detect_agents_finds_gemini_legacy_hooks(tmp_path: Path) -> None:
    """Gemini handlers from checkout-based installers count as installed."""
    handler = {
        "type": "command",
        "name": "vauxhall-idle",
        "command": "python /x/hooks/gemini/telemetry_hook.py",
    }
    _write_settings(tmp_path, "gemini", _with_handler(handler))

    assert _by_agent(tmp_path)["gemini"]["installed"] is True


def test_detect_agents_ignores_foreign_handlers(tmp_path: Path) -> None:
    """Another tool's handler is not Vauxhall's."""
    _write_settings(
        tmp_path, "claude", _with_handler({"type": "command", "command": "echo hi"})
    )

    entry = _by_agent(tmp_path)["claude"]

    assert entry["installed"] is False
    assert entry["error"] is None


def test_detect_agents_reports_malformed_settings(tmp_path: Path) -> None:
    """Unparsable settings are reported for that agent only."""
    path = tmp_path / agents.INSTALLERS["claude"].settings_path
    path.parent.mkdir()
    path.write_text("{")
    (tmp_path / ".codex").mkdir()

    found = _by_agent(tmp_path)

    assert found["claude"]["installed"] is False
    assert isinstance(found["claude"]["error"], str)
    assert found["claude"]["error"]
    assert found["codex"] == {
        "agent": "codex",
        "name": "Codex",
        "detected": True,
        "installed": False,
        "error": None,
    }


def test_detect_agents_reports_wrong_shape(tmp_path: Path) -> None:
    """Settings the installer would reject are reported with its message."""
    _write_settings(tmp_path, "claude", {"hooks": []})

    assert (
        _by_agent(tmp_path)["claude"]["error"]
        == "Claude Code hooks must be a JSON object"
    )


def test_detect_agents_writes_nothing(tmp_path: Path) -> None:
    """Detection creates no directory, backup, or file."""
    module = agents.INSTALLERS["codex"].module
    command = installation.build_hook_command(Path("/venv/bin/python"), module)
    _write_settings(
        tmp_path, "codex", _with_handler({"type": "command", "command": command})
    )
    malformed = tmp_path / agents.INSTALLERS["claude"].settings_path
    malformed.parent.mkdir()
    malformed.write_text("{")
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    agents.detect_agents(tmp_path)

    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_detect_agents_reports_an_unreadable_workspace(unsearchable_dir: Path) -> None:
    """A workspace that can't be checked is reported per agent, not raised."""
    found = agents.detect_agents(unsearchable_dir)

    assert [entry["detected"] for entry in found] == [False, False, False]
    assert all(entry["error"] for entry in found)
