# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Main entry point for the Vauxhall Dashboard application."""

from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from pyloid import Pyloid
from pyloid.serve import pyloid_serve

from vauxhall.core.logging import get_logger, setup_logging
from vauxhall.core.telemetry import telemetry_validation_error
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber

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
        self._updates_lock = Lock()
        self._dispatch_lock = Lock()
        self.ipc = DashboardIPC(on_ready_callback=self._on_frontend_ready)
        self.pending_updates: deque[dict[str, Any]] = deque(
            maxlen=settings.dashboard.pending_update_limit
        )
        self.discarded_pending_updates = 0
        self.last_status: str | None = None
        self.mqtt: DashboardSubscriber | None = None

    def drain_queue(self) -> None:
        """Forward all queued updates to the frontend."""
        self._drain_pending_updates(mark_ready=False)

    def _on_frontend_ready(self) -> None:
        """Atomically transfer queued updates when the frontend becomes ready."""
        self._drain_pending_updates(mark_ready=True)

    def _drain_pending_updates(self, *, mark_ready: bool) -> None:
        """Snapshot pending state under lock, then forward it to the frontend."""
        with self._dispatch_lock:
            with self._updates_lock:
                if mark_ready:
                    self.ipc.is_ready = True
                last_status = self.last_status
                pending_updates = list(self.pending_updates)
                self.pending_updates.clear()

            if last_status:
                self.window.invoke("status-update", last_status)
            if pending_updates:
                logger.info("Draining %d queued updates.", len(pending_updates))
            for pending_update in pending_updates:
                self.window.invoke("agent-update", pending_update)

    def on_telemetry(self, data: object) -> None:
        """Handle telemetry data received from MQTT.

        If the frontend is ready, the data is invoked immediately.
        Otherwise, it is queued until the frontend signals readiness.

        Args:
            data: The decoded telemetry data.
        """
        try:
            error = telemetry_validation_error(data)
            if error is not None:
                logger.warning("Rejected telemetry: %s", error)
                return

            assert isinstance(data, dict)
            telemetry = dict(data)

            with self._updates_lock:
                if not self.ipc.is_ready:
                    logger.debug("Queuing telemetry for agent: %s", telemetry["agent"])
                    if len(self.pending_updates) == self.pending_updates.maxlen:
                        self.discarded_pending_updates += 1
                        if (
                            self.discarded_pending_updates
                            & (self.discarded_pending_updates - 1)
                            == 0
                        ):
                            logger.warning(
                                "Discarded oldest pending telemetry update; "
                                "total discarded: %d",
                                self.discarded_pending_updates,
                            )
                    self.pending_updates.append(telemetry)
                    return

            with self._dispatch_lock:
                self.window.invoke("agent-update", telemetry)
        except Exception:
            logger.exception("Error in on_telemetry")

    def on_status(self, message: str) -> None:
        """Handle status updates from MQTT.

        Args:
            message: The status message.
        """
        try:
            with self._updates_lock:
                self.last_status = message
                is_ready = self.ipc.is_ready
            if is_ready:
                with self._dispatch_lock:
                    self.window.invoke("status-update", message)
        except Exception:
            logger.exception("Error in on_status")

    def run(self) -> None:
        """Run the application."""
        self.window = self.app.create_window(
            title=settings.dashboard.window_title,
            width=settings.dashboard.width,
            height=settings.dashboard.height,
            dev_tools=settings.dashboard.debug,
            IPCs=[self.ipc],
        )

        self.mqtt = DashboardSubscriber(self.on_telemetry, self.on_status)
        try:
            self.mqtt.start()

            ui_dir = Path(__file__).parent / "ui"

            ui_dir_abs = ui_dir.resolve()
            url = pyloid_serve(str(ui_dir_abs), port=settings.dashboard.port)
            logger.info("Serving UI from %s at %s", ui_dir_abs, url)

            self.window.load_url(url)
            self.window.show_and_focus()
            self.app.run()
        finally:
            self.mqtt.stop()
            logger.info("Vauxhall Dashboard shutting down...")


def main() -> None:
    """Run the Vauxhall Dashboard application."""
    setup_logging(level=settings.logging.level)
    logger.info("Starting Vauxhall Dashboard...")

    app = Pyloid(app_name="Vauxhall Dashboard")
    dashboard = DashboardApp(app)
    dashboard.run()


if __name__ == "__main__":
    main()
