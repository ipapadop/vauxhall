# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests that MQTT callbacks and the UI thread never wait on each other.

The deadlock scenarios run in a child process with a real Qt event loop:
run in the pytest process, a regression would hang the suite.
"""

import os
import subprocess
import sys
import threading

from PySide6.QtCore import QCoreApplication

from vauxhall.dashboard.app import queue_to_ui_thread

CHILD = """
import faulthandler
import sys
import threading
import time
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal, Slot

from vauxhall.dashboard.app import DashboardApp

faulthandler.dump_traceback_later(10, exit=True)
qapp = QCoreApplication(sys.argv)


class BlockingWindow(QObject):
    # Like Pyloid 0.27.2's BrowserWindow.invoke: a caller on another thread
    # waits until the UI thread has run the command.
    _request = Signal(object)

    def __init__(self):
        super().__init__()
        self.events = []
        self._request.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def invoke(self, name, data=None):
        if threading.current_thread() is threading.main_thread():
            self.events.append(name)
            return
        done = threading.Event()
        self._request.emit((name, done))
        done.wait()

    @Slot(object)
    def _run(self, request):
        name, done = request
        self.events.append(name)
        done.set()


dashboard = DashboardApp(MagicMock())
dashboard.window = BlockingWindow()
dashboard.ipc.is_ready = True
event = {
    "schema_version": 1,
    "agent": "Codex",
    "workspace": "/workspace",
    "session_id": "session-1",
    "state": "Acting",
    "details": {},
}


def on_ui_thread():
    # Stands in for the MQTT network thread delivering telemetry while the
    # UI thread is busy.
    network = threading.Thread(target=dashboard.on_telemetry, args=(event,))
    network.start()
    time.sleep(0.3)
    if sys.argv[1] == "save-settings":
        dashboard.save_settings({"dashboard": {"stale_threshold": 300}})
    # Stands in for paho's loop_stop(), which joins the network thread on a
    # broker change and at shutdown.
    network.join(timeout=2)
    print("network thread finished:", not network.is_alive())
    QTimer.singleShot(200, qapp.quit)


QTimer.singleShot(0, on_ui_thread)
qapp.exec()
print("delivered:", " ".join(dashboard.window.events))
"""


def run_child(scenario: str) -> list[str]:
    """Run one scenario in a child process.

    Args:
        scenario: ``save-settings`` or ``join``.

    Returns:
        The child's output lines.
    """
    result = subprocess.run(
        [sys.executable, "-c", CHILD, scenario],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_settings_save_during_telemetry_delivers_both() -> None:
    """A settings save while telemetry is in flight freezes neither thread."""
    lines = run_child("save-settings")

    assert "network thread finished: True" in lines
    assert "delivered: agent-update settings-changed" in lines


def test_ui_thread_can_join_the_network_thread() -> None:
    """Stopping MQTT from the UI thread doesn't wait on a delivery to it."""
    lines = run_child("join")

    assert "network thread finished: True" in lines
    assert "delivered: agent-update" in lines


def test_queue_runs_events_on_its_thread_in_posting_order() -> None:
    """Events posted from another thread run later, on the queue's thread."""
    application = QCoreApplication.instance() or QCoreApplication([])
    ran: list[tuple[str, object, bool]] = []
    post = queue_to_ui_thread(
        lambda name, data: ran.append(
            (name, data, threading.current_thread() is threading.main_thread())
        )
    )

    worker = threading.Thread(target=post, args=("agent-update", {"n": 1}))
    worker.start()
    worker.join(timeout=2)
    post("settings-changed", {"n": 2})
    assert not worker.is_alive()
    assert ran == []

    application.processEvents()

    assert ran == [
        ("agent-update", {"n": 1}, True),
        ("settings-changed", {"n": 2}, True),
    ]
