import pyperclip
from pyloid.ipc import PyloidIPC, Bridge


class DashboardIPC(PyloidIPC):
    def __init__(self, on_ready_callback=None):
        super().__init__()
        self.is_ready = False
        self.on_ready_callback = on_ready_callback

    @Bridge(result=bool)
    def set_ready(self) -> bool:
        """Called by JS when frontend is ready to receive events."""
        self.is_ready = True
        if self.on_ready_callback:
            self.on_ready_callback()
        return True

    @Bridge(str, result=bool)
    def copy_to_clipboard(self, text: str) -> bool:
        """Copies text to the system clipboard."""
        try:
            pyperclip.copy(text)
            print(f"Copied to clipboard: {text}")
            return True
        except Exception as e:
            print(f"Clipboard error: {e}")
            return False
