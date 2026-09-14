# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Main entry point for the Vauxhall Dashboard application."""

import logging
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from pyloid import Pyloid
from pyloid.serve import pyloid_serve

from vauxhall.core.config import ConfigurationError
from vauxhall.core.config_store import check_user_config, save_user_config
from vauxhall.core.logging import get_logger, setup_logging
from vauxhall.core.telemetry import telemetry_validation_error
from vauxhall.dashboard.config import DashboardConfig
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.dashboard.settings_editor import (
    DASHBOARD_FILE,
    HOOKS_FILE,
    apply_mode,
    changed_fields,
    error_field,
    hook_config_type,
)

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
        self._settings_lock = Lock()
        self.ipc = DashboardIPC(
            on_ready_callback=self._on_frontend_ready,
            on_save_settings=self.save_settings,
        )
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
        """Forward valid telemetry, or queue it until the frontend is ready."""
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
                        discarded = self.discarded_pending_updates
                        if discarded & (discarded - 1) == 0:
                            logger.warning(
                                "Discarded oldest pending telemetry update; "
                                "total discarded: %d",
                                discarded,
                            )
                    self.pending_updates.append(telemetry)
                    return

            with self._dispatch_lock:
                self.window.invoke("agent-update", telemetry)
        except Exception:
            logger.exception("Error in on_telemetry")

    def on_status(self, message: str) -> None:
        """Record an MQTT status and forward it when the frontend is ready."""
        try:
            with self._updates_lock:
                self.last_status = message
                is_ready = self.ipc.is_ready
            if is_ready:
                with self._dispatch_lock:
                    self.window.invoke("status-update", message)
        except Exception:
            logger.exception("Error in on_status")

    def save_settings(
        self, changes: dict[str, dict[str, object]], *, update_hooks: bool
    ) -> dict[str, Any]:
        """Save settings changes and apply those that don't need a restart.

        Both files are validated before either is written, so an invalid
        dashboard or hooks change saves nothing.

        Args:
            changes: New values, grouped by section.
            update_hooks: Whether to also save MQTT changes to the hooks file.

        Returns:
            dict[str, Any]: The outcome for the settings editor.
        """
        hook_changes = (
            {"mqtt": changes["mqtt"]} if update_hooks and changes.get("mqtt") else None
        )
        with self._settings_lock:
            file = "dashboard"
            try:
                check_user_config(DASHBOARD_FILE, DashboardConfig, changes)
                if hook_changes:
                    file = "hooks"
                    check_user_config(HOOKS_FILE, hook_config_type(), hook_changes)
                    file = "dashboard"
                save_user_config(DASHBOARD_FILE, DashboardConfig, changes)
                new_config = DashboardConfig.load()
            except (ConfigurationError, OSError) as error:
                logger.warning("Settings not saved: %s", error)
                return {
                    "ok": False,
                    "error": str(error),
                    "field": error_field(str(error)),
                    "file": file,
                }

            hooks_error = None
            if hook_changes:
                try:
                    save_user_config(HOOKS_FILE, hook_config_type(), hook_changes)
                except (ConfigurationError, OSError) as error:
                    logger.warning("Hooks configuration not saved: %s", error)
                    hooks_error = str(error)

            changed = changed_fields(settings, new_config)
            reconnecting = self._apply_settings(new_config, changed)

        return {
            "ok": True,
            "restart_required": [
                key for key in changed if apply_mode(key) == "restart"
            ],
            "reconnecting": reconnecting,
            "hooks_updated": hook_changes is not None and hooks_error is None,
            "hooks_error": hooks_error,
        }

    def _apply_settings(self, new_config: DashboardConfig, changed: list[str]) -> bool:
        """Replace the running settings and apply changes that take effect now.

        Returns:
            bool: Whether the MQTT subscriber was restarted.
        """
        settings.mqtt = new_config.mqtt
        settings.logging = new_config.logging
        settings.dashboard = new_config.dashboard
        if not changed:
            return False

        if "logging.level" in changed:
            logging.getLogger().setLevel(new_config.logging.level)

        reconnecting = self.mqtt is not None and any(
            apply_mode(key) == "reconnect" for key in changed
        )
        if reconnecting:
            self._reconnect()

        with self._updates_lock:
            is_ready = self.ipc.is_ready
        if is_ready:
            with self._dispatch_lock:
                self.window.invoke(
                    "settings-changed",
                    {
                        "stale_threshold": settings.dashboard.stale_threshold,
                        "max_active_agents": settings.dashboard.max_active_agents,
                    },
                )
        return reconnecting

    def _reconnect(self) -> None:
        """Replace the MQTT subscriber with one using the current broker settings."""
        assert self.mqtt is not None
        self.mqtt.stop()
        self.mqtt = DashboardSubscriber(
            self.on_telemetry, self.on_status, settings.mqtt.host, settings.mqtt.port
        )
        try:
            self.mqtt.start()
        except Exception:
            logger.exception("Could not reconnect to the MQTT broker")

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

            ui_dir = (Path(__file__).parent / "ui").resolve()
            url = pyloid_serve(str(ui_dir), port=settings.dashboard.port)
            logger.info("Serving UI from %s at %s", ui_dir, url)

            self.window.load_url(url)
            self.window.show_and_focus()
            self.app.run()
        finally:
            # The window is gone once the UI loop exits; queue any late updates.
            with self._updates_lock:
                self.ipc.is_ready = False
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
