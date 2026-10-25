# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Main entry point for the Vauxhall Dashboard application."""

import logging
import os
import sys
from collections import deque
from collections.abc import Callable, MutableMapping
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any

from pyloid import Pyloid
from pyloid.serve import pyloid_serve
from PySide6.QtCore import QObject, Qt, Signal, Slot

from vauxhall.core.config import ConfigurationError
from vauxhall.core.config_store import check_user_config, save_user_config
from vauxhall.core.logging import get_logger, setup_logging
from vauxhall.core.telemetry import telemetry_validation_error
from vauxhall.dashboard import USER_CHROMIUM_FLAGS
from vauxhall.dashboard.config import DashboardConfig
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.graphics import set_graphics_backend
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.dashboard.settings_editor import (
    DASHBOARD_FILE,
    HOOKS_FILE,
    apply_mode,
    changed_fields,
    error_field,
    hook_changes_for,
    hook_config_type,
)
from vauxhall.dashboard.ui_state import (
    load_ui_state,
    update_ui_state,
    visible_position,
    window_geometry,
)

logger = get_logger(__name__)

UI_DIR = (Path(__file__).parent / "ui").resolve()
ICON_FILE = UI_DIR / "icon.png"

WindowEvent = Callable[[str, object], None]


class _UIThreadQueue(QObject):
    """Runs window events on the thread that created it, in the order posted."""

    _posted = Signal(str, object)

    def __init__(self, handler: WindowEvent) -> None:
        """Connect the queue to its handler.

        Args:
            handler: Called on this object's thread with each posted event.
        """
        super().__init__()
        self._handler = handler
        # Queued even when posted from this thread, so every event keeps its
        # place in one order.
        self._posted.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def post(self, name: str, data: object) -> None:
        """Queue an event and return without waiting for it to run.

        Args:
            name: The window event name.
            data: The event payload.
        """
        self._posted.emit(name, data)

    @Slot(str, object)
    def _run(self, name: str, data: object) -> None:
        """Hand a queued event to the handler.

        Args:
            name: The window event name.
            data: The event payload.
        """
        self._handler(name, data)


def queue_to_ui_thread(handler: WindowEvent) -> WindowEvent:
    """Return a non-blocking poster that runs ``handler`` on the UI thread.

    Args:
        handler: The function that sends one event to the window.

    Returns:
        WindowEvent: Queues an event for ``handler`` and returns at once.
    """
    return _UIThreadQueue(handler).post


class DashboardApp:
    """Encapsulates the Dashboard application state and logic."""

    def __init__(
        self,
        app: Pyloid,
        queue_to_ui: Callable[[WindowEvent], WindowEvent] = queue_to_ui_thread,
    ) -> None:
        """Initialize the Dashboard application.

        Must run on the UI thread, which then runs every window event.

        Args:
            app: The Pyloid application instance.
            queue_to_ui: Wraps the window-event handler in a poster that runs
                it on the UI thread without waiting.
        """
        self.app = app
        self.window: Any = None
        # Pyloid's window.invoke() waits for the UI thread, so only the UI
        # thread calls it; everyone else posts and moves on. The UI thread
        # alone reads and writes readiness, the pending updates, the last
        # status, and the outbox, so they need no lock.
        self._post = queue_to_ui(self._dispatch)
        self.ipc = DashboardIPC(
            on_ready_callback=self._on_frontend_ready,
            on_save_settings=self.save_settings,
            on_notify=self._notify,
            on_send_prompt=self.send_prompt,
        )
        self.pending_updates: deque[dict[str, Any]] = deque(
            maxlen=settings.dashboard.pending_update_limit
        )
        self.discarded_pending_updates = 0
        self.last_status: str | None = None
        self._outbox: deque[tuple[str, object]] = deque()
        self._sending = False
        self.mqtt: DashboardSubscriber | None = None
        self._subscriber_generation = 0

    def _on_frontend_ready(self) -> None:
        """Mark the frontend ready and send it the last status and queued updates.

        Runs on the UI thread, like every event, so no event can run between
        marking the frontend ready and queuing the backlog ahead of it.
        """
        self.ipc.is_ready = True
        if self.last_status:
            self._outbox.append(("status-update", self.last_status))
        if self.pending_updates:
            logger.info("Draining %d queued updates.", len(self.pending_updates))
        self._outbox.extend(("agent-update", update) for update in self.pending_updates)
        self.pending_updates.clear()
        self._send_outbox()

    def _dispatch(self, name: str, data: object) -> None:
        """Send one posted event to the window, or hold it. Runs on the UI thread.

        Args:
            name: The window event name.
            data: The event payload.
        """
        if name == "status-update" and isinstance(data, tuple):
            generation, message = data
            if generation != self._subscriber_generation:
                return
            self.last_status = data = message
        # Before readiness, and after the window closes, only telemetry is
        # kept; the frontend gets the last status when it becomes ready.
        if not self.ipc.is_ready:
            if name == "agent-update" and isinstance(data, dict):
                self._hold(data)
            return
        self._outbox.append((name, data))
        self._send_outbox()

    def _hold(self, telemetry: dict[str, Any]) -> None:
        """Keep telemetry until the frontend is ready, dropping the oldest.

        Args:
            telemetry: The validated telemetry.
        """
        logger.debug("Queuing telemetry for agent: %s", telemetry["agent"])
        if len(self.pending_updates) == self.pending_updates.maxlen:
            self.discarded_pending_updates += 1
            discarded = self.discarded_pending_updates
            if discarded & (discarded - 1) == 0:
                logger.warning(
                    "Discarded oldest pending telemetry update; total discarded: %d",
                    discarded,
                )
        self.pending_updates.append(telemetry)

    def _send_outbox(self) -> None:
        """Send the outbox to the window in order. Runs on the UI thread."""
        # window.invoke() runs a nested event loop that can run the next
        # posted event. That event only joins the outbox, so sends never nest
        # and leave in the order they were queued.
        if self._sending:
            return
        self._sending = True
        try:
            # Shutdown's own Pyloid calls run nested event loops that can
            # reach events posted before the window closed. Sending one to
            # the deleted web view makes Pyloid wait forever for a result.
            while self._outbox and self.ipc.is_ready:
                name, data = self._outbox.popleft()
                # A denylist save posted its settings-changed after this
                # update, so the frontend removes the card before this would
                # revive it.
                if (
                    name == "agent-update"
                    and isinstance(data, dict)
                    and data["agent"] in settings.dashboard.agent_denylist
                ):
                    logger.debug(
                        "Dropping denylisted agent telemetry: %s", data["agent"]
                    )
                    continue
                try:
                    self.window.invoke(name, data)
                except Exception:
                    logger.exception("Could not send %s to the window", name)
        finally:
            self._sending = False

    def on_telemetry(self, data: object) -> None:
        """Post valid telemetry to the UI thread, which holds it until ready.

        Args:
            data: The telemetry payload received from MQTT.
        """
        try:
            error = telemetry_validation_error(data)
            if error is not None:
                logger.warning("Rejected telemetry: %s", error)
                return

            assert isinstance(data, dict)
            telemetry = dict(data)

            if telemetry["agent"] in settings.dashboard.agent_denylist:
                logger.debug(
                    "Dropping denylisted agent telemetry: %s", telemetry["agent"]
                )
                return

            self._post("agent-update", telemetry)
        except Exception:
            logger.exception("Error in on_telemetry")

    def _notify(self, title: str, message: str) -> None:
        """Show an OS notification for a card that started needing attention.

        Args:
            title: The notification title.
            message: The notification body.
        """
        self.app.show_notification(title, message)

    def send_prompt(self, agent: str, session_id: str, text: str) -> dict[str, Any]:
        """Publish a prompt for one agent session.

        Args:
            agent: The agent name of the session's card.
            session_id: The session identity of the card.
            text: The prompt to send.

        Returns:
            dict[str, Any]: ``ok`` with the acknowledgment ``id`` on success,
                otherwise ``ok`` false with an ``error`` to show.
        """
        subscriber = self.mqtt
        if subscriber is None:
            return {"ok": False, "error": "Not connected to the broker"}
        try:
            return {"ok": True, "id": subscriber.send_prompt(agent, session_id, text)}
        except (ValueError, ConnectionError) as error:
            logger.warning("Prompt not sent: %s", error)
            return {"ok": False, "error": str(error)}

    def on_ack(self, ack: dict[str, str]) -> None:
        """Forward a relay's acknowledgment of a prompt to the frontend.

        Args:
            ack: The validated acknowledgment, with ``id``, ``status``, and
                optionally ``reason``. It is dropped when the frontend isn't
                ready, since no card can be waiting on it then.
        """
        try:
            self._post("prompt-ack", ack)
        except Exception:
            logger.exception("Error in on_ack")

    def on_status(self, message: str, generation: int) -> None:
        """Post an MQTT status to the UI thread, which records and forwards it.

        Args:
            message: The status to show.
            generation: The generation of the subscriber that reported it. The
                UI thread drops a status from a subscriber since replaced.
        """
        try:
            self._post("status-update", (generation, message))
        except Exception:
            logger.exception("Error in on_status")

    def _status_callback(self) -> Callable[[str], None]:
        """Return the status callback for a new subscriber, retiring older ones.

        A discarded subscriber's network thread can be inside a callback,
        past its stopping check, and post its status after the replacement's.
        Runs on the UI thread, which also checks the generation.

        Returns:
            Callable[[str], None]: Posts a status tagged with the new generation.
        """
        self._subscriber_generation += 1
        return partial(self.on_status, generation=self._subscriber_generation)

    def save_settings(
        self, changes: dict[str, dict[str, object]], *, update_hooks: bool = False
    ) -> dict[str, Any]:
        """Save settings changes and apply those that don't need a restart.

        Both files are validated before either is written, so an invalid
        dashboard or hooks change saves nothing.

        Args:
            changes: New dashboard values, grouped by section.
            update_hooks: Whether to also save the editable MQTT values that
                differ from the ones the hooks use to the hooks file.

        Returns:
            dict[str, Any]: The outcome for the settings editor.
        """
        file = "dashboard"
        hook_changes: dict[str, dict[str, object]] = {}
        try:
            check_user_config(DASHBOARD_FILE, DashboardConfig, changes)
            if update_hooks:
                file = "hooks"
                hook_changes = hook_changes_for(changes, settings.mqtt)
                if hook_changes:
                    check_user_config(HOOKS_FILE, hook_config_type(), hook_changes)
                file = "dashboard"
            if changes:
                save_user_config(DASHBOARD_FILE, DashboardConfig, changes)
            new_config = DashboardConfig.load()
        except (ConfigurationError, OSError) as error:
            logger.warning("Settings not saved: %s", error)
            return {
                "ok": False,
                "error": str(error),
                # The named field belongs to the hooks file, not the form.
                "field": error_field(str(error)) if file == "dashboard" else None,
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
            "hooks_updated": bool(hook_changes) and hooks_error is None,
            "hooks_error": hooks_error,
        }

    def _apply_settings(self, new_config: DashboardConfig, changed: list[str]) -> bool:
        """Replace the running settings and apply changes that take effect now.

        Args:
            new_config: The saved configuration to run with.
            changed: The "section.key" fields that differ from the running ones.

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

        self._post(
            "settings-changed",
            {
                "stale_threshold": settings.dashboard.stale_threshold,
                "max_active_agents": settings.dashboard.max_active_agents,
                "agent_denylist": settings.dashboard.agent_denylist,
            },
        )
        return reconnecting

    def _reconnect(self) -> None:
        """Replace the MQTT subscriber with one using the current broker settings."""
        assert self.mqtt is not None
        self.mqtt.discard()
        self.mqtt = DashboardSubscriber(
            self.on_telemetry,
            self._status_callback(),
            settings.mqtt.host,
            settings.mqtt.port,
            ack_callback=self.on_ack,
        )
        try:
            self.mqtt.start()
        except Exception:
            logger.exception("Could not reconnect to the MQTT broker")

    def _create_window(self) -> dict[str, Any]:
        """Create the window with its saved size and, if still on screen, position.

        Returns:
            dict[str, Any]: The window geometry saved by the previous run.
        """
        saved_window = load_ui_state().get("window", {})
        # Pyloid reads the icon while the window loads, so it has to be set
        # before the window exists.
        self.app.set_icon(str(ICON_FILE))
        self.window = self.app.create_window(
            title=settings.dashboard.window_title,
            width=saved_window.get("width", settings.dashboard.width),
            height=saved_window.get("height", settings.dashboard.height),
            dev_tools=settings.dashboard.debug,
            IPCs=[self.ipc],
        )
        if {"x", "y"} <= saved_window.keys():
            screens = [
                monitor.available_geometry() for monitor in self.app.get_all_monitors()
            ]
            position = visible_position(saved_window, screens)
            if position is not None:
                self.window.set_position(*position)
        return saved_window

    def _save_window_state(self, previous: dict[str, Any]) -> None:
        """Remember the window's size, position, and maximized state.

        Args:
            previous: The last saved window state, kept for values the window
                cannot report.
        """
        try:
            update_ui_state({"window": window_geometry(self.window, previous)})
        except Exception:
            logger.exception("Could not save the dashboard window state")

    def run(self) -> None:
        """Run the application."""
        saved_window = self._create_window()

        self.mqtt = DashboardSubscriber(
            self.on_telemetry, self._status_callback(), ack_callback=self.on_ack
        )
        try:
            self.mqtt.start()

            url = pyloid_serve(str(UI_DIR), port=settings.dashboard.port)
            logger.info("Serving UI from %s at %s", UI_DIR, url)

            self.window.load_url(url)
            self.window.show_and_focus()
            if saved_window.get("maximized"):
                self.window.maximize()
            self.app.run()
        finally:
            # The window is gone once the UI loop exits; hold any late updates.
            self.ipc.is_ready = False
            self._save_window_state(saved_window)
            self.mqtt.stop()
            logger.info("Vauxhall Dashboard shutting down...")


def _use_utf8_output() -> None:
    """Keep non-ASCII output from killing whoever writes it.

    The UI server prints a banner containing emoji. Windows consoles default to
    a code page that cannot represent them, and the resulting UnicodeEncodeError
    stops the server before it serves anything.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            with suppress(AttributeError, OSError, ValueError):
                stream.reconfigure(  # pyright: ignore[reportAttributeAccessIssue]
                    encoding="utf-8", errors="replace"
                )


# Pyloid turns off certificate checks for every page the window loads. The UI
# is served over plain HTTP, so they serve no purpose here.
_INSECURE_PYLOID_FLAGS = frozenset(
    {"--ignore-certificate-errors", "--allow-insecure-localhost"}
)


def _set_chromium_flags(
    environ: MutableMapping[str, str] = os.environ,
    user_flags: str = USER_CHROMIUM_FLAGS,
) -> None:
    """Drop Pyloid's certificate overrides and append the user's flags.

    Qt reads the variable when the application starts, so this must run
    before ``Pyloid``. The user's flags are kept as given.

    Args:
        environ: The environment to update.
        user_flags: The flags the user set before Pyloid's import.
    """
    pyloid_flags = environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    flags = [flag for flag in pyloid_flags if flag not in _INSECURE_PYLOID_FLAGS]
    environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([*flags, user_flags]).strip()


def main() -> None:
    """Run the Vauxhall Dashboard application."""
    _use_utf8_output()
    _set_chromium_flags()
    setup_logging(level=settings.logging.level)
    logger.info("Starting Vauxhall Dashboard...")
    set_graphics_backend(settings.dashboard.graphics_backend)

    app = Pyloid(app_name="Vauxhall Dashboard")
    dashboard = DashboardApp(app)
    dashboard.run()


if __name__ == "__main__":
    main()
