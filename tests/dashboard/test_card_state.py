# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for remembered dashboard card identities."""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config_store import user_config_path
from vauxhall.dashboard.card_state import (
    STATE_FILE,
    clean_cards,
    load_saved_cards,
    save_cards,
)
from vauxhall.dashboard.config import UIConfig, dashboard_settings
from vauxhall.dashboard.ipc import DashboardIPC

pytestmark = pytest.mark.usefixtures("isolated_cwd")

CARD = {
    "agent": "Claude Code",
    "workspace": "/home/user/project",
    "session_id": "abc123",
    "state": "Idle",
    "env": "local",
    "last_seen": 1000,
}


def state_path() -> Path:
    """Return the per-user dashboard card state file.

    Returns:
        The path of the card state file.
    """
    return user_config_path(STATE_FILE)


def write_state(content: str | bytes) -> Path:
    """Write raw content to the dashboard card state file.

    Args:
        content: The case's raw file content.

    Returns:
        The path written.
    """
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_load_without_file_returns_empty_list() -> None:
    """A missing state file means no saved cards."""
    assert load_saved_cards() == []


@pytest.mark.parametrize("content", ["{", b"\xff"])
def test_load_ignores_corrupt_file(
    content: str | bytes, caplog: pytest.LogCaptureFixture
) -> None:
    """A corrupt or malformed state file falls back to an empty list with a warning.

    Args:
        content: The case's raw file content.
        caplog: Pytest log capture fixture.
    """
    write_state(content)

    with caplog.at_level(logging.WARNING):
        assert load_saved_cards() == []

    assert "Ignoring" in caplog.text


def test_load_treats_non_list_cards_value_as_empty() -> None:
    """A valid JSON object whose 'cards' isn't a list yields no cards, silently."""
    write_state(json.dumps({"cards": "x"}))

    assert load_saved_cards() == []


def test_clean_keeps_a_valid_card() -> None:
    """A card with every valid field is kept as-is."""
    assert clean_cards([CARD]) == [CARD]


def test_clean_drops_card_without_env() -> None:
    """A card without env is kept, just without that key."""
    card = {k: v for k, v in CARD.items() if k != "env"}
    assert clean_cards([card]) == [card]


@pytest.mark.parametrize(
    "changes",
    [
        {"agent": ""},
        {"agent": "x" * 129},
        {"workspace": ""},
        {"session_id": "x" * 257},
        {"state": "STALE"},
        {"state": "bogus"},
        {"env": "cloud"},
        {"last_seen": -1},
        {"last_seen": "1000"},
        {"last_seen": True},
        {"last_seen": None},
    ],
)
def test_clean_drops_invalid_card(changes: dict[str, object]) -> None:
    """A card with an out-of-bounds or wrong-typed field is dropped.

    Args:
        changes: Overrides applied to a valid card to make it invalid.
    """
    assert clean_cards([{**CARD, **changes}]) == []


@pytest.mark.parametrize("data", [None, {}, "cards", [1, "x", None]])
def test_clean_rejects_non_list_or_non_dict_entries(data: object) -> None:
    """Anything that isn't a list of card objects yields no cards.

    Args:
        data: The case's malformed input.
    """
    assert clean_cards(data) == []


def test_clean_deduplicates_by_identity_keeping_newest() -> None:
    """A repeated identity keeps only the entry with the greatest last_seen."""
    older = {**CARD, "state": "Acting", "last_seen": 100}
    newer = {**CARD, "state": "Error", "last_seen": 200}

    assert clean_cards([older, newer]) == [newer]
    assert clean_cards([newer, older]) == [newer]


def test_clean_caps_card_count() -> None:
    """More than the defensive maximum of cards is truncated."""
    cards = [
        {**CARD, "session_id": f"session-{i}", "last_seen": i} for i in range(1001)
    ]

    assert len(clean_cards(cards)) == 1000


def test_save_writes_cleaned_cards_atomically() -> None:
    """Saving writes only the valid, cleaned cards to disk."""
    save_cards([CARD, {"agent": ""}])

    assert json.loads(state_path().read_text(encoding="utf-8")) == {"cards": [CARD]}


def test_save_creates_state_file() -> None:
    """The first save creates the configuration directory and file."""
    save_cards([CARD])

    assert state_path().exists()


def test_load_returns_previously_saved_cards() -> None:
    """A saved list round-trips through load."""
    save_cards([CARD])

    assert load_saved_cards() == [CARD]


def test_ipc_get_saved_cards_returns_saved_cards() -> None:
    """The bridge returns the saved card list as JSON."""
    save_cards([CARD])

    assert json.loads(DashboardIPC().get_saved_cards()) == [CARD]


def test_ipc_get_saved_cards_omits_denylisted_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A card for a currently denylisted agent is left out, like live telemetry."""
    other = {**CARD, "agent": "Codex", "session_id": "other"}
    save_cards([CARD, other])
    monkeypatch.setattr(
        dashboard_settings, "dashboard", UIConfig(agent_denylist=[CARD["agent"]])
    )

    assert json.loads(DashboardIPC().get_saved_cards()) == [other]


def test_ipc_save_cards_round_trips() -> None:
    """A card list saved through the bridge is returned by a later load."""
    ipc = DashboardIPC()

    assert ipc.save_cards(json.dumps([CARD]))

    assert json.loads(ipc.get_saved_cards()) == [CARD]


@pytest.mark.parametrize("payload", ["not json", "{}", '{"cards": []}'])
def test_ipc_save_cards_rejects_invalid_payload(payload: str) -> None:
    """A payload that isn't a JSON array is rejected without writing.

    Args:
        payload: The case's payload.
    """
    assert DashboardIPC().save_cards(payload) is False
    assert not state_path().exists()


def test_ipc_save_cards_reports_write_failure() -> None:
    """A state file that cannot be written is reported as not saved."""
    with patch("vauxhall.dashboard.ipc.save_cards", side_effect=OSError("read-only")):
        assert DashboardIPC().save_cards("[]") is False
