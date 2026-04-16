# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""IPC Bridge for the Vauxhall Dashboard."""

import webbrowser
from typing import Any, Callable, Optional

import pyperclip
from pyloid.ipc import Bridge, PyloidIPC

from vauxhall.config import settings
from vauxhall.logging_config import get_logger

logger = get_logger(__name__)


class DashboardIPC(PyloidIPC):
    """IPC Bridge for communication between Python and the web frontend."""

    def __init__(self, on_ready_callback: Optional[Callable[[], Any]] = None) -> None:
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
            f"Frontend requested stale threshold: {settings.dashboard.stale_threshold}s"
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
            logger.info(f"Opening URL in system browser: {url}")
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
            return False

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
            logger.info(f"Copied to clipboard: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")
            return False
