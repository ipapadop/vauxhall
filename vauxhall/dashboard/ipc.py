# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""IPC Bridge for the Vauxhall Dashboard."""

import json
import webbrowser
from collections.abc import Callable
from typing import Any

import pyperclip
from pyloid.ipc import Bridge, PyloidIPC

from vauxhall.core.config import ConfigurationError
from vauxhall.core.logging import get_logger
from vauxhall.dashboard.card_state import load_saved_cards, save_cards
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.settings_editor import describe_settings
from vauxhall.dashboard.ui_state import (
    frontend_preferences,
    load_ui_state,
    update_ui_state,
)

logger = get_logger(__name__)


def _is_section_map(value: object) -> bool:
    """Return whether a value maps section names to objects of field values.

    Args:
        value: The candidate settings changes received from the frontend.

    Returns:
        Whether the value has the shape the settings bridge expects.
    """
    return isinstance(value, dict) and all(
        isinstance(values, dict) for values in value.values()
    )


def _json_object(payload: str) -> dict[str, Any] | None:
    """Parse a bridge payload that must be a JSON object.

    Args:
        payload: The JSON text received from the frontend.

    Returns:
        The parsed object, or ``None`` when the payload is not a JSON object.
    """
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _json_array(payload: str) -> list[Any] | None:
    """Parse a bridge payload that must be a JSON array.

    Args:
        payload: The JSON text received from the frontend.

    Returns:
        The parsed array, or ``None`` when the payload is not a JSON array.
    """
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, list) else None


class DashboardIPC(PyloidIPC):
    """IPC Bridge for communication between Python and the web frontend."""

    def __init__(
        self,
        on_ready_callback: Callable[[], Any] | None = None,
        on_save_settings: Callable[..., dict[str, Any]] | None = None,
        on_notify: Callable[[str, str], Any] | None = None,
    ) -> None:
        """Initialize the IPC bridge.

        Args:
            on_ready_callback: Optional function to call when the frontend is ready.
            on_save_settings: Optional function that saves settings changes,
                called with the changes and an ``update_hooks`` keyword.
            on_notify: Optional function that shows a desktop notification,
                called with a title and a message.
        """
        super().__init__()
        self.is_ready = False
        self.on_ready_callback = on_ready_callback
        self.on_save_settings = on_save_settings
        self.on_notify = on_notify

    @Bridge(result=bool)
    def ping(self) -> bool:
        """Verify bridge health.

        Returns:
            bool: Always True if reachable.
        """
        logger.debug("Received ping from frontend.")
        return True

    @Bridge(result=bool)
    def set_ready(self) -> bool:
        """Mark the frontend ready, draining queued updates on the first call.

        Returns:
            bool: Always True.
        """
        if self.is_ready:
            return True
        if self.on_ready_callback:
            self.on_ready_callback()
        self.is_ready = True
        logger.info("Frontend signaled readiness.")
        return True

    @Bridge(result=int)
    def get_stale_threshold(self) -> int:
        """Retrieve the stale threshold in seconds from the configuration.

        Returns:
            int: The stale threshold in seconds.
        """
        logger.debug(
            "Frontend requested stale threshold: %ds",
            settings.dashboard.stale_threshold,
        )
        return settings.dashboard.stale_threshold

    @Bridge(result=int)
    def get_max_active_agents(self) -> int:
        """Retrieve the maximum number of active dashboard cards.

        Returns:
            The configured maximum number of cards.
        """
        logger.debug(
            "Frontend requested maximum active agents: %d",
            settings.dashboard.max_active_agents,
        )
        return settings.dashboard.max_active_agents

    @Bridge(result=str)
    def get_settings(self) -> str:
        """Describe every dashboard setting for the settings editor.

        Returns:
            str: JSON with the fields, save paths, and any hooks file error, or
                with an ``error`` when the dashboard configuration is malformed.
        """
        try:
            return json.dumps(describe_settings(settings))
        except ConfigurationError as error:
            logger.warning("Could not describe settings: %s", error)
            return json.dumps({"error": str(error)})

    @Bridge(str, result=str)
    def save_settings(self, payload: str) -> str:
        """Save settings changes sent by the settings editor.

        Args:
            payload: JSON object with ``changes`` (new dashboard values grouped
                by section) and an optional boolean ``update_hooks``.

        Returns:
            str: JSON describing the outcome.
        """
        request = _json_object(payload) or {}
        changes = request.get("changes")
        update_hooks = request.get("update_hooks", False)
        if (
            self.on_save_settings is None
            or not _is_section_map(changes)
            or not isinstance(update_hooks, bool)
        ):
            return json.dumps({"ok": False, "error": "Invalid settings request"})

        try:
            result = self.on_save_settings(changes, update_hooks=update_hooks)
        except Exception:
            logger.exception("Failed to save settings")
            return json.dumps({"ok": False, "error": "Settings could not be saved"})
        return json.dumps(result)

    @Bridge(result=str)
    def get_ui_state(self) -> str:
        """Return the saved view preferences.

        Returns:
            str: JSON with any saved ``theme``, ``sort``, ``history_filter``,
                ``attention_first``, and ``notify``.
        """
        return json.dumps(frontend_preferences(load_ui_state()))

    @Bridge(str, result=bool)
    def save_ui_state(self, payload: str) -> bool:
        """Save view preferences sent by the frontend.

        Unknown keys, invalid values, and window geometry are ignored.

        Args:
            payload: JSON object with any of ``theme``, ``sort``,
                ``history_filter``, ``attention_first``, and ``notify``.

        Returns:
            bool: True if the request was valid and the state file was written.
        """
        changes = _json_object(payload)
        if changes is None:
            return False
        try:
            update_ui_state(frontend_preferences(changes))
        except OSError:
            logger.exception("Could not save dashboard preferences")
            return False
        return True

    @Bridge(result=str)
    def get_saved_cards(self) -> str:
        """Return the card identities saved from the previous run.

        Cards for a currently denylisted agent are left out, the same as live
        telemetry for that agent.

        Returns:
            str: JSON array of saved cards, each with ``agent``, ``workspace``,
                ``session_id``, ``state``, ``last_seen``, and optionally ``env``.
        """
        denylist = settings.dashboard.agent_denylist
        cards = [card for card in load_saved_cards() if card["agent"] not in denylist]
        return json.dumps(cards)

    @Bridge(str, result=bool)
    def save_cards(self, payload: str) -> bool:
        """Save the current card identities sent by the frontend.

        Invalid entries are dropped rather than rejecting the whole request,
        so one malformed card doesn't lose the rest.

        Args:
            payload: JSON array of the frontend's current cards.

        Returns:
            bool: True if the request was valid and the state file was written.
        """
        cards = _json_array(payload)
        if cards is None:
            return False
        try:
            save_cards(cards)
        except OSError:
            logger.exception("Could not save dashboard card state")
            return False
        return True

    @Bridge(str, result=bool)
    def open_url(self, url: str) -> bool:
        """Open a URL in the system's default browser.

        Args:
            url: The URL to open.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            logger.info("Opening URL in system browser: %s", url)
            webbrowser.open(url)
        except Exception:
            logger.exception("Failed to open URL")
            return False
        else:
            return True

    @Bridge(str, str, result=bool)
    def notify(self, title: str, message: str) -> bool:
        """Show a desktop notification for a card that started needing attention.

        Args:
            title: The notification title.
            message: The notification body.

        Returns:
            bool: True if a notification callback is registered and it succeeds.
        """
        if self.on_notify is None:
            return False
        try:
            self.on_notify(title, message)
        except Exception:
            logger.exception("Failed to show notification")
            return False
        else:
            return True

    @Bridge(str, result=bool)
    def copy_to_clipboard(self, text: str) -> bool:
        """Copy text to the system clipboard.

        Args:
            text: The text to copy.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            pyperclip.copy(text)
            logger.info("Copied to clipboard: %s...", text[:50])
        except Exception:
            logger.exception("Failed to copy to clipboard")
            return False
        else:
            return True
