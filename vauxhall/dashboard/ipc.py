# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""IPC Bridge for the Vauxhall Dashboard."""

import webbrowser
from collections.abc import Callable
from typing import Any

import pyperclip
from pyloid.ipc import Bridge, PyloidIPC

from vauxhall.config import settings
from vauxhall.logging_config import get_logger

logger = get_logger(__name__)


class DashboardIPC(PyloidIPC):
    """IPC Bridge for communication between Python and the web frontend."""

    def __init__(self, on_ready_callback: Callable[[], Any] | None = None) -> None:
        """Initialize the IPC bridge.

        Args:
            on_ready_callback: Optional function to call when the frontend is ready.
        """
        super().__init__()
        self.is_ready = False
        self.on_ready_callback = on_ready_callback

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
        """Called by JavaScript when the frontend is ready to receive events.

        Returns:
            bool: Always True.
        """
        self.is_ready = True
        logger.info("Frontend signaled readiness.")
        if self.on_ready_callback:
            self.on_ready_callback()
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

    @Bridge(str, result=bool)
    def open_url(self, url: str) -> bool:
        """Opens a URL in the system's default browser.

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
        """Copies text to the system clipboard.

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

