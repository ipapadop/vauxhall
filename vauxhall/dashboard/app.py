# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Main entry point for the Vauxhall Dashboard application."""

import os
from typing import Any

from pyloid import Pyloid
from pyloid.serve import pyloid_serve

from vauxhall.config import settings
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


def main() -> None:
    """Run the Vauxhall Dashboard application.

    This function initializes the Pyloid application, sets up the window and IPC,
    starts the MQTT subscriber, and runs the application loop.
    """
    setup_logging(level=settings.logging.level)
    logger.info("Starting Vauxhall Dashboard...")

    app = Pyloid(app_name="Vauxhall Dashboard")

    # Queue for updates received before frontend is ready
    pending_updates: list[dict[str, Any]] = []
    last_status: str | None = None

    def drain_queue() -> None:
        """Forward all queued updates to the frontend."""
        if last_status:
            window.invoke("status-update", last_status)
        if pending_updates:
            logger.info(f"Draining {len(pending_updates)} queued updates.")
        while pending_updates:
            p = pending_updates.pop(0)
            window.invoke("agent-update", p)

    ipc = DashboardIPC(on_ready_callback=drain_queue)

    window = app.create_window(
        title=settings.dashboard.window_title,
        width=settings.dashboard.width,
        height=settings.dashboard.height,
        IPCs=[ipc],
    )

    # Optional: suppressed due to bug in pyloid v0.27.2
    # icon_path = os.path.join(os.path.dirname(__file__), "ui", "icon.png")
    # if os.path.exists(icon_path):
    #     app.set_icon(icon_path)

    # Callback to emit data to JS
    def on_telemetry(data: dict[str, Any]) -> None:
        """Handle telemetry data received from MQTT.

        If the frontend is ready, the data is invoked immediately.
        Otherwise, it is queued until the frontend signals readiness.

        Args:
            data: The telemetry data dictionary.
        """
        try:
            # Basic schema validation
            required_fields = ["agent", "workspace", "state"]
            if not all(field in data for field in required_fields):
                logger.warning(f"Received malformed telemetry: {data}")
                return

            if ipc.is_ready:
                # Drain queue if any (just in case)
                drain_queue()
                window.invoke("agent-update", data)
            else:
                logger.debug(f"Queuing telemetry for agent: {data.get('agent')}")
                pending_updates.append(data)
        except Exception as e:
            logger.exception(f"Error in on_telemetry: {e}")

    def on_status(message: str) -> None:
        """Handle status updates from MQTT."""
        nonlocal last_status
        last_status = message
        try:
            if ipc.is_ready:
                window.invoke("status-update", message)
        except Exception as e:
            logger.exception(f"Error in on_status: {e}")

    mqtt = DashboardSubscriber(on_telemetry, on_status)
    mqtt.start()

    ui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "ui"))
    url = pyloid_serve(ui_dir)
    logger.info(f"Serving UI from {ui_dir} at {url}")

    window.load_url(url)
    window.show_and_focus()
    app.run()
    logger.info("Vauxhall Dashboard shutting down...")
    mqtt.stop()


if __name__ == "__main__":
    main()
