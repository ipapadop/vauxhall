"""Main entry point for the Vauxhall Dashboard application."""

import os
from typing import Any

from pyloid import Pyloid
from pyloid.serve import pyloid_serve

from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber


def main() -> None:
    """Run the Vauxhall Dashboard application.

    This function initializes the Pyloid application, sets up the window and IPC,
    starts the MQTT subscriber, and runs the application loop.
    """
    app = Pyloid(app_name="Vauxhall Dashboard")

    # Queue for updates received before frontend is ready
    pending_updates: list[dict[str, Any]] = []

    def drain_queue() -> None:
        """Forward all queued updates to the frontend."""
        while pending_updates:
            p = pending_updates.pop(0)
            window.invoke("agent-update", p)

    ipc = DashboardIPC(on_ready_callback=drain_queue)

    window = app.create_window(
        title="Vauxhall Agent Dashboard",
        width=1000,
        height=800,
        IPCs=[ipc],
    )

    ui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "ui"))

    # Tray Menu configuration
    tray_icon_path = os.path.join(ui_dir, "icon.png")
    if os.path.exists(tray_icon_path):
        app.set_tray_icon(tray_icon_path)
    
    app.set_tray_menu_items([
        {"label": "Show Dashboard", "callback": window.show},
        {"label": "Hide Dashboard", "callback": window.hide},
        {"type": "separator"},
        {"label": "Exit", "callback": app.quit},
    ])

    # Optional: suppressed due to bug in pyloid v0.27.2
    # icon_path = os.path.join(os.path.dirname(__file__), "ui", "icon.png")
    # if os.path.exists(icon_path):
    #     app.set_icon(icon_path)

    # Callback to emit data to JS
    def on_telemetry(data: dict[str, Any]) -> None:
        """Handle telemetry data with error boundaries.

        If the frontend is ready, the data is invoked immediately.
        Otherwise, it is queued until the frontend signals readiness.

        Args:
            data: The telemetry data dictionary.
        """
        try:
            # Basic schema validation
            required_fields = ["agent", "workspace", "state"]
            if not all(field in data for field in required_fields):
                print(f"ERROR: Received malformed telemetry: {data}")
                return

            if ipc.is_ready:
                # Drain queue if any (just in case)
                drain_queue()
                window.invoke("agent-update", data)
            else:
                pending_updates.append(data)
        except Exception as e:
            print(f"CRITICAL: Error in on_telemetry: {e}")

    mqtt = DashboardSubscriber(on_telemetry)
    mqtt.start()

    url = pyloid_serve(ui_dir)

    window.load_url(url)
    window.show_and_focus()
    app.run()
    mqtt.stop()


if __name__ == "__main__":
    main()
