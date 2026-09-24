# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Remember dashboard card identities between runs, not their telemetry content.

Only the fields needed to redraw the grid on the next start are kept: agent,
workspace, session_id, the last real state, env, and the last-seen time.
Prompts, messages, commands, tool arguments, errors, tokens, duration, and
activity history are never written here; see docs/privacy.md.
"""

from typing import Any

from vauxhall.core.config import load_config_data
from vauxhall.core.config_store import user_config_path, write_json_atomically
from vauxhall.core.logging import get_logger
from vauxhall.core.telemetry import SUPPORTED_STATES

logger = get_logger(__name__)

STATE_FILE = "dashboard_cards.json"

_STRING_FIELDS = ("agent", "workspace", "session_id")
_STRING_LIMITS = {"agent": 128, "workspace": 4096, "session_id": 256}
_ENVS = {"local", "remote"}
# A defensive cap on a hand-edited or corrupt file; the frontend already
# bounds what it saves to the configured max_active_agents.
_MAX_CARDS = 1000


def _is_last_seen(value: object) -> bool:
    """Return whether a value is a usable last-seen timestamp.

    Args:
        value: The candidate timestamp, in epoch milliseconds.

    Returns:
        Whether the value is a non-negative integer.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_valid_card(card: object) -> bool:
    """Return whether a card entry has the expected identity fields.

    Args:
        card: The candidate card entry.

    Returns:
        Whether every required field is present and within its bounds.
    """
    if not isinstance(card, dict):
        return False
    for field in _STRING_FIELDS:
        value = card.get(field)
        if not isinstance(value, str) or not 0 < len(value) <= _STRING_LIMITS[field]:
            return False
    if card.get("state") not in SUPPORTED_STATES:
        return False
    if "env" in card and card["env"] not in _ENVS:
        return False
    return _is_last_seen(card.get("last_seen"))


def clean_cards(data: object) -> list[dict[str, Any]]:
    """Keep only valid card entries, deduplicated by identity.

    Args:
        data: Decoded card list, possibly from a hand-edited or outdated file.

    Returns:
        list[dict[str, Any]]: The valid entries, newest last-seen kept for a
            repeated identity, capped to a defensive maximum count.
    """
    if not isinstance(data, list):
        return []

    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for card in data:
        if not _is_valid_card(card):
            continue
        identity = (card["agent"], card["workspace"], card["session_id"])
        existing = by_identity.get(identity)
        if existing is None or card["last_seen"] >= existing["last_seen"]:
            by_identity[identity] = card

    cards = list(by_identity.values())[:_MAX_CARDS]
    return [
        {
            key: card[key]
            for key in ("agent", "workspace", "session_id", "state", "last_seen")
        }
        | ({"env": card["env"]} if "env" in card else {})
        for card in cards
    ]


def load_saved_cards() -> list[dict[str, Any]]:
    """Load saved card identities, ignoring a missing, unreadable, or corrupt file.

    Returns:
        list[dict[str, Any]]: The valid saved card entries.
    """
    path = user_config_path(STATE_FILE)
    try:
        return clean_cards(load_config_data(path).get("cards"))
    except ValueError as error:
        logger.warning("Ignoring unreadable dashboard card state %s: %s", path, error)
        return []


def save_cards(cards: object) -> None:
    """Validate and atomically save card identities, replacing any saved list.

    Args:
        cards: The card entries to save.

    Raises:
        OSError: If the state file cannot be written.
    """
    path = user_config_path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomically(path, {"cards": clean_cards(cards)})
