import os
from pyloid import Pyloid
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber

from pyloid.serve import pyloid_serve


def main():
    app = Pyloid(app_name="Vauxhall Dashboard")

    # Queue for updates received before frontend is ready
    pending_updates = []

    def drain_queue():
        while pending_updates:
            p = pending_updates.pop(0)
            window.invoke("agent-update", p)

    ipc = DashboardIPC(on_ready_callback=drain_queue)

    window = app.create_window(
        title="Vauxhall Agent Dashboard",
        width=1000,
        height=800,
        IPCs=[ipc]
    )

    # Optional: suppressed due to bug in pyloid v0.27.2
    # icon_path = os.path.join(os.path.dirname(__file__), "ui", "icon.png")
    # if os.path.exists(icon_path):
    #     app.set_icon(icon_path)

    # Callback to emit data to JS
    def on_telemetry(data):
        if ipc.is_ready:
            # Drain queue if any (just in case)
            drain_queue()
            window.invoke("agent-update", data)
        else:
            pending_updates.append(data)


    mqtt = DashboardSubscriber(on_telemetry)
    mqtt.start()

    ui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "ui"))
    url = pyloid_serve(ui_dir)

    window.load_url(url)
    window.show_and_focus()
    app.run()
    mqtt.stop()


if __name__ == "__main__":
    main()
