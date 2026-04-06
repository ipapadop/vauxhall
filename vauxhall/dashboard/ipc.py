import pyperclip
from pyloid.ipc import PyloidIPC, Bridge

class DashboardIPC(PyloidIPC):
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
