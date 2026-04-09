"""IPC Bridge for the Vauxhall Dashboard."""

from typing import Any, Callable, Optional

import pyperclip
from pyloid.ipc import Bridge, PyloidIPC


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
        return True

    @Bridge(result=bool)
    def set_ready(self) -> bool:
        """Called by JavaScript when the frontend is ready to receive events.

        Returns:
            bool: Always True.
        """
        self.is_ready = True
        if self.on_ready_callback:
            self.on_ready_callback()
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
            return True
        except Exception:
            return False
