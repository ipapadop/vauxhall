import os
from pyloid import Pyloid
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber

def main():
    app = Pyloid(app_name="Vauxhall Dashboard")
    ipc = DashboardIPC()
    
    window = app.create_window(
        title="Vauxhall Agent Dashboard",
        width=1000,
        height=800,
        IPCs=[ipc]
    )

    # Queue for updates received before frontend is ready
    pending_updates = []

    # Optional: Set icon to suppress "Icon is not set" warning
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "icon.png")
    if os.path.exists(icon_path):
        app.set_icon(icon_path)

    # Callback to emit data to JS
    def on_telemetry(data):
        print(f"DEBUG: Telemetry received: {data['agent']}")
        if ipc.is_ready:
            # Drain queue if any
            while pending_updates:
                p = pending_updates.pop(0)
                window.invoke("agent-update", p)
                print(f"DEBUG: Sent queued update: {p['agent']}")
            window.invoke("agent-update", data)
            print(f"DEBUG: Sent live update: {data['agent']}")
        else:
            print(f"DEBUG: Frontend not ready, queuing update for {data['agent']}")
            pending_updates.append(data)

    mqtt = DashboardSubscriber(on_telemetry)
    mqtt.start()

    ui_dir = os.path.join(os.path.dirname(__file__), "ui")
    index_path = os.path.join(ui_dir, "index.html")

    window.load_file(index_path)
    window.show_and_focus()
    app.run()
    mqtt.stop()

if __name__ == "__main__":
    main()
