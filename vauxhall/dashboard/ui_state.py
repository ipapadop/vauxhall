# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Remember dashboard view preferences and window geometry between runs."""

from collections.abc import Mapping, Sequence
from dataclasses import fields
from threading import Lock
from typing import Any

from vauxhall.core.config import load_config_data
from vauxhall.core.config_store import user_config_path, write_json_atomically
from vauxhall.core.logging import get_logger
from vauxhall.dashboard.config import UIConfig

logger = get_logger(__name__)

STATE_FILE = "dashboard_state.json"

# Preferences the frontend reads and saves. The page ignores sort and filter
# values it doesn't offer, so only their shape is checked here. The "window"
# entry is written only by Python.
FRONTEND_KEYS = ("theme", "sort", "history_filter", "attention_first", "notify")
# Preferences stored as booleans rather than the bounded strings the rest use.
BOOLEAN_KEYS = {"attention_first", "notify"}
THEMES = {"dark", "light"}
MAX_PREFERENCE_LENGTH = 64
# Saved window sizes follow the limits of the configured size.
_SIZE_LIMITS = {
    field.name: (field.metadata["min"], field.metadata["max"])
    for field in fields(UIConfig)
    if field.name in {"width", "height"}
}
# How much of the window's top edge must be on a screen to restore its position.
VISIBLE_WIDTH = 100
VISIBLE_HEIGHT = 40

# Frontend saves and the shutdown window save each load, merge, and replace the
# file; holding this lock for the whole update keeps one from discarding the other.
_update_lock = Lock()


def _is_int(value: object) -> bool:
    """Return whether a value is an integer but not a boolean.

    Args:
        value: The candidate value.

    Returns:
        Whether the value is an integer.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _is_valid_preference(key: str, value: object) -> bool:
    """Return whether a frontend preference value has an acceptable form.

    Args:
        key: The preference name.
        value: The candidate value.

    Returns:
        Whether the value is a bool for a boolean preference, or otherwise a
        bounded string, and a known theme for "theme".
    """
    if key in BOOLEAN_KEYS:
        return isinstance(value, bool)
    if not isinstance(value, str) or not 0 < len(value) <= MAX_PREFERENCE_LENGTH:
        return False
    return key != "theme" or value in THEMES


def _clean_window(window: object) -> dict[str, Any]:
    """Keep only valid window size, position, and maximized values.

    Args:
        window: The candidate window geometry.

    Returns:
        The values that are in range, dropping the rest.
    """
    if not isinstance(window, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, (minimum, maximum) in _SIZE_LIMITS.items():
        value = window.get(key)
        if _is_int(value) and minimum <= value <= maximum:
            cleaned[key] = value
    for key in ("x", "y"):
        if _is_int(window.get(key)):
            cleaned[key] = window[key]
    if isinstance(window.get("maximized"), bool):
        cleaned["maximized"] = window["maximized"]
    return cleaned


def clean_ui_state(data: object) -> dict[str, Any]:
    """Keep only known preferences with valid values.

    Args:
        data: Decoded state, possibly from a hand-edited or outdated file.

    Returns:
        dict[str, Any]: The valid preferences and window geometry.
    """
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, Any] = {
        key: data[key]
        for key in FRONTEND_KEYS
        if _is_valid_preference(key, data.get(key))
    }
    window = _clean_window(data.get("window"))
    if window:
        cleaned["window"] = window
    return cleaned


def frontend_preferences(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the preferences the frontend may read or save.

    Args:
        state: The saved UI state.

    Returns:
        The subset of the state the frontend is allowed to see.
    """
    return {key: state[key] for key in FRONTEND_KEYS if key in state}


def load_ui_state() -> dict[str, Any]:
    """Load saved preferences, ignoring a missing, unreadable, or corrupt file.

    Returns:
        dict[str, Any]: The valid saved preferences and window geometry.
    """
    path = user_config_path(STATE_FILE)
    try:
        return clean_ui_state(load_config_data(path))
    except ValueError as error:
        # ConfigurationError covers unreadable files, invalid JSON, and
        # non-objects; UnicodeDecodeError covers files that aren't UTF-8.
        logger.warning("Ignoring unreadable dashboard state %s: %s", path, error)
        return {}


def update_ui_state(changes: object) -> dict[str, Any]:
    """Merge valid changes into the saved state and write it atomically.

    Invalid or unknown values in ``changes`` are ignored and keep any saved
    value. Concurrent updates run one at a time, so none is lost.

    Args:
        changes: New preferences or window geometry.

    Returns:
        dict[str, Any]: The saved state.

    Raises:
        OSError: If the state file cannot be written.
    """
    with _update_lock:
        state = load_ui_state()
        state.update(clean_ui_state(changes))
        path = user_config_path(STATE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomically(path, state)
    return state


def visible_position(
    window: Mapping[str, Any], screens: Sequence[Mapping[str, int]]
) -> tuple[int, int] | None:
    """Return the saved window position if its top edge is still on a screen.

    Args:
        window: Saved window geometry with ``x``, ``y``, and ``width``.
        screens: Available screen areas with ``x``, ``y``, ``width``, and ``height``.

    Returns:
        tuple[int, int] | None: The position to restore, or None to keep the default.
    """
    if not {"x", "y", "width"} <= window.keys():
        return None
    x, y, width = window["x"], window["y"], window["width"]
    for screen in screens:
        overlap = min(x + width, screen["x"] + screen["width"]) - max(x, screen["x"])
        top_on_screen = (
            screen["y"] <= y <= screen["y"] + screen["height"] - VISIBLE_HEIGHT
        )
        if top_on_screen and overlap >= VISIBLE_WIDTH:
            return x, y
    return None


def window_geometry(window: Any, previous: Mapping[str, Any]) -> dict[str, Any]:  # noqa: ANN401
    """Describe a Pyloid window for saving.

    Args:
        window: The Pyloid browser window.
        previous: The window geometry saved earlier.

    Returns:
        dict[str, Any]: The window's size, position, and maximized state. A
            maximized window keeps its previously saved normal size and position.
    """
    if window.is_maximized():
        return {**previous, "maximized": True}
    return {**window.get_size(), **window.get_position(), "maximized": False}
