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
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.settings_editor import describe_settings

logger = get_logger(__name__)


class DashboardIPC(PyloidIPC):
    """IPC Bridge for communication between Python and the web frontend."""

    def __init__(
        self,
        on_ready_callback: Callable[[], Any] | None = None,
        on_save_settings: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the IPC bridge.

        Args:
            on_ready_callback: Optional function to call when the frontend is ready.
            on_save_settings: Optional function that saves settings changes,
                called with the changes and an ``update_hooks`` keyword.
        """
        super().__init__()
        self.is_ready = False
        self.on_ready_callback = on_ready_callback
        self.on_save_settings = on_save_settings

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
        """Retrieve the maximum number of active dashboard cards."""
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
            payload: JSON object with ``changes`` (new values grouped by
                section) and an optional boolean ``update_hooks``.

        Returns:
            str: JSON describing the outcome.
        """
        try:
            request = json.loads(payload)
        except json.JSONDecodeError:
            request = None
        if not isinstance(request, dict):
            request = {}
        changes = request.get("changes")
        update_hooks = request.get("update_hooks", False)
        if (
            self.on_save_settings is None
            or not isinstance(changes, dict)
            or not all(isinstance(values, dict) for values in changes.values())
            or not isinstance(update_hooks, bool)
        ):
            return json.dumps({"ok": False, "error": "Invalid settings request"})

        try:
            result = self.on_save_settings(changes, update_hooks=update_hooks)
        except Exception:
            logger.exception("Failed to save settings")
            return json.dumps({"ok": False, "error": "Settings could not be saved"})
        return json.dumps(result)

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
