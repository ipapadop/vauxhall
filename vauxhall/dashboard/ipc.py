from pyloid.ipc import PyloidIPC, Bridge

class DashboardIPC(PyloidIPC):
    @Bridge(str, result=bool)
    def copy_to_clipboard(self, text: str) -> bool:
        """Handled in a later task."""
        print(f"IPC received: {text}")
        return True
