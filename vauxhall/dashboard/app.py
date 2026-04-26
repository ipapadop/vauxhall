# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Main entry point for the Vauxhall Dashboard application."""

from pathlib import Path
from typing import Any

from pyloid import Pyloid
from pyloid.serve import pyloid_serve

from vauxhall.config import settings
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


class DashboardApp:
    """Encapsulates the Dashboard application state and logic."""

    def __init__(self, app: Pyloid) -> None:
        """Initialize the Dashboard application.

        Args:
            app: The Pyloid application instance.
        """
        self.app = app
        self.window: Any = None
        self.ipc = DashboardIPC(on_ready_callback=self.drain_queue)
        self.pending_updates: list[dict[str, Any]] = []
        self.last_status: str | None = None
        self.mqtt: DashboardSubscriber | None = None

    def drain_queue(self) -> None:
        """Forward all queued updates to the frontend."""
        if self.last_status:
            self.window.invoke("status-update", self.last_status)
        if self.pending_updates:
            logger.info("Draining %d queued updates.", len(self.pending_updates))
        while self.pending_updates:
            p = self.pending_updates.pop(0)
            self.window.invoke("agent-update", p)

    def on_telemetry(self, data: dict[str, Any]) -> None:
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
                logger.warning("Received malformed telemetry: %s", data)
                return

            if self.ipc.is_ready:
                # Drain queue if any (just in case)
                self.drain_queue()
                self.window.invoke("agent-update", data)
            else:
                logger.debug("Queuing telemetry for agent: %s", data.get("agent"))
                self.pending_updates.append(data)
        except Exception:
            logger.exception("Error in on_telemetry")

    def on_status(self, message: str) -> None:
        """Handle status updates from MQTT.

        Args:
            message: The status message.
        """
        self.last_status = message
        try:
            if self.ipc.is_ready:
                self.window.invoke("status-update", message)
        except Exception:
            logger.exception("Error in on_status")

    def run(self) -> None:
        """Run the application."""
        self.window = self.app.create_window(
            title=settings.dashboard.window_title,
            width=settings.dashboard.width,
            height=settings.dashboard.height,
            IPCs=[self.ipc],
        )

        self.mqtt = DashboardSubscriber(self.on_telemetry, self.on_status)
        self.mqtt.start()

        ui_dir = Path(__file__).parent / "ui"

        ui_dir_abs = ui_dir.resolve()
        url = pyloid_serve(str(ui_dir_abs))
        logger.info("Serving UI from %s at %s", ui_dir_abs, url)

        self.window.load_url(url)
        self.window.show_and_focus()
        self.app.run()
        logger.info("Vauxhall Dashboard shutting down...")
        self.mqtt.stop()


def main() -> None:
    """Run the Vauxhall Dashboard application."""
    setup_logging(level=settings.logging.level)
    logger.info("Starting Vauxhall Dashboard...")

    app = Pyloid(app_name="Vauxhall Dashboard")
    dashboard = DashboardApp(app)
    dashboard.run()


if __name__ == "__main__":
    main()
