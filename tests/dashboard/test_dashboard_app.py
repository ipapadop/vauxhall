# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for Vauxhall Dashboard components."""

import json
import unittest
from copy import deepcopy
from threading import Event, Thread
from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest

# Mock dependencies that might not be available or should be isolated
sys_modules_patch = patch.dict(
    "sys.modules",
    {
        "pyperclip": MagicMock(),
        "paho": MagicMock(),
        "paho.mqtt": MagicMock(),
        "paho.mqtt.client": MagicMock(),
    },
)
sys_modules_patch.start()

from vauxhall.dashboard.app import ICON_FILE, DashboardApp  # noqa: E402
from vauxhall.dashboard.ipc import DashboardIPC  # noqa: E402
from vauxhall.dashboard.mqtt_client import DashboardSubscriber  # noqa: E402


def valid_event(**overrides: object) -> dict[str, object]:
    """Return a valid version-one dashboard telemetry event.

    Returns:
        The event.
    """
    event: dict[str, object] = {
        "schema_version": 1,
        "agent": "Codex",
        "workspace": "/workspace",
        "session_id": "session-1",
        "state": "Thinking",
        "details": {},
    }
    event.update(overrides)
    return event


class TestDashboardComponents(unittest.TestCase):
    """Tests for IPC and Subscriber components."""

    def valid_telemetry(self) -> dict[str, Any]:
        """Return one valid schema-v1 dashboard update.

        Returns:
            The update.
        """
        return {
            "schema_version": 1,
            "agent": "TestAgent",
            "workspace": "/path",
            "session_id": "native:session-1",
            "state": "Acting",
            "details": {},
        }

    def setUp(self) -> None:
        """Set up the test environment."""
        self.mock_app = MagicMock()
        self.dashboard = DashboardApp(self.mock_app)
        self.dashboard.window = MagicMock()

    def test_on_telemetry_missing_fields(self) -> None:
        """Verify that telemetry missing required fields is dropped."""
        self.dashboard.ipc.is_ready = True

        # Missing workspace
        missing_workspace = self.valid_telemetry()
        del missing_workspace["workspace"]
        self.dashboard.on_telemetry(missing_workspace)
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 0

        # Missing state
        missing_state = self.valid_telemetry()
        del missing_state["state"]
        self.dashboard.on_telemetry(missing_state)
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 0

    @patch("vauxhall.dashboard.app.pyloid_serve", return_value="http://localhost")
    def test_run_uses_configured_pyloid_window_settings(
        self, mock_serve: MagicMock
    ) -> None:
        """Dashboard startup passes its supported settings to Pyloid.

        Args:
            mock_serve: Mock replacing ``vauxhall.dashboard.app.pyloid_serve``.
        """
        with (
            patch("vauxhall.dashboard.app.DashboardSubscriber"),
            patch("vauxhall.dashboard.app.settings") as mock_settings,
        ):
            mock_settings.dashboard.window_title = "Configured dashboard"
            mock_settings.dashboard.width = 1280
            mock_settings.dashboard.height = 720
            mock_settings.dashboard.debug = True
            mock_settings.dashboard.port = 9090

            self.mock_app.run.side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                self.dashboard.run()

        self.mock_app.create_window.assert_called_once_with(
            title="Configured dashboard",
            width=1280,
            height=720,
            dev_tools=True,
            IPCs=[self.dashboard.ipc],
        )
        mock_serve.assert_called_once_with(ANY, port=9090)

    @patch("vauxhall.dashboard.app.pyloid_serve", return_value="http://localhost")
    def test_run_sets_the_shipped_icon_before_the_window_loads(
        self, mock_serve: MagicMock
    ) -> None:
        """Pyloid reads the icon while loading the window, so it must exist first.

        Args:
            mock_serve: Mock replacing ``vauxhall.dashboard.app.pyloid_serve``.
        """
        with patch("vauxhall.dashboard.app.DashboardSubscriber"):
            self.mock_app.run.side_effect = KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                self.dashboard.run()

        assert ICON_FILE.is_file()
        self.mock_app.set_icon.assert_called_once_with(str(ICON_FILE))
        called = [name for name, _, _ in self.mock_app.mock_calls]
        assert called.index("set_icon") < called.index("create_window")
        mock_serve.assert_called_once()

    def test_on_telemetry_queuing(self) -> None:
        """Verify that telemetry queued when IPC is not ready and flushed on drain."""
        self.dashboard.ipc.is_ready = False

        valid_data = self.valid_telemetry()
        self.dashboard.on_telemetry(valid_data)

        # Should be queued, not invoked
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 1
        assert self.dashboard.pending_updates[0] == valid_data

        # Drain queue
        self.dashboard.drain_queue()
        self.dashboard.window.invoke.assert_called_once_with("agent-update", valid_data)
        assert len(self.dashboard.pending_updates) == 0

    def test_on_telemetry_forwards_valid_data_immediately(self) -> None:
        """Verify that valid telemetry reaches ready frontend IPC immediately."""
        self.dashboard.ipc.is_ready = True
        valid_data = self.valid_telemetry()
        expected_data = deepcopy(valid_data)

        self.dashboard.on_telemetry(valid_data)

        self.dashboard.window.invoke.assert_called_once_with(
            "agent-update", expected_data
        )
        forwarded_data = self.dashboard.window.invoke.call_args.args[1]
        assert forwarded_data == expected_data
        assert forwarded_data is not expected_data
        assert not self.dashboard.pending_updates

    def test_on_telemetry_rejects_unversioned_and_unsupported_messages(self) -> None:
        """Only supported schema-v1 telemetry may reach dashboard state."""
        self.dashboard.ipc.is_ready = False
        unversioned = self.valid_telemetry()
        del unversioned["schema_version"]
        unsupported = {**self.valid_telemetry(), "schema_version": 2}

        with self.assertLogs("vauxhall.dashboard.app", level="WARNING") as logs:
            self.dashboard.on_telemetry(unversioned)
            self.dashboard.on_telemetry(unsupported)

        assert not self.dashboard.pending_updates
        self.dashboard.window.invoke.assert_not_called()
        assert "schema_version is required" in logs.output[0]
        assert "unsupported schema_version; expected 1" in logs.output[1]

    def test_on_telemetry_rejection_log_does_not_include_payload(self) -> None:
        """Protocol warnings must not leak any raw payload content."""
        schema_sentinel = 2718281828
        invalid = {
            **self.valid_telemetry(),
            "schema_version": schema_sentinel,
            "agent": "sentinel-agent",
            "workspace": "sentinel-workspace",
            "session_id": "sentinel-session",
            "state": "sentinel-state",
            "details": {
                "prompt": "sentinel-prompt",
                "cmd": "sentinel-command",
            },
            "extra": "sentinel-extra",
        }

        with self.assertLogs("vauxhall.dashboard.app", level="WARNING") as logs:
            self.dashboard.on_telemetry(invalid)

        assert logs.output == [
            (
                "WARNING:vauxhall.dashboard.app:Rejected telemetry: "
                "unsupported schema_version; expected 1"
            )
        ]
        for sentinel in (
            str(schema_sentinel),
            "sentinel-agent",
            "sentinel-workspace",
            "sentinel-session",
            "sentinel-state",
            "sentinel-prompt",
            "sentinel-command",
            "sentinel-extra",
        ):
            assert sentinel not in logs.output[0]

    def test_ipc_copy_to_clipboard(self) -> None:
        """Test that the IPC bridge correctly calls pyperclip."""
        ipc = DashboardIPC()
        with patch("vauxhall.dashboard.ipc.pyperclip.copy") as mock_copy:
            result = ipc.copy_to_clipboard("test text")
            mock_copy.assert_called_once_with("test text")
            assert result

    def test_ipc_copy_to_clipboard_error(self) -> None:
        """Test that clipboard errors are handled gracefully."""
        ipc = DashboardIPC()
        with patch(
            "vauxhall.dashboard.ipc.pyperclip.copy", side_effect=Exception("error")
        ):
            result = ipc.copy_to_clipboard("test text")
            assert not result

    def test_subscriber_on_message(self) -> None:
        """Test that the subscriber correctly forwards MQTT messages to the callback."""
        callback = MagicMock()
        subscriber = DashboardSubscriber(callback, MagicMock())

        # Create a mock message
        msg: Any = MagicMock()
        data = {
            "schema_version": 1,
            "agent": "Gemini",
            "workspace": "/home/user/project",
            "session_id": "native:session-1",
            "state": "Thinking",
            "details": {},
        }
        msg.payload = json.dumps(data).encode()

        # Call the private method directly for testing
        subscriber._on_message(None, None, msg)

        callback.assert_called_once_with(data)

    def test_subscriber_on_message_invalid_json(self) -> None:
        """Test that invalid JSON messages are ignored by the subscriber."""
        callback = MagicMock()
        subscriber = DashboardSubscriber(callback, MagicMock())

        # Create a mock message with invalid JSON
        msg: Any = MagicMock()
        msg.payload = b"invalid json"

        # Should not raise exception, but also not call callback
        subscriber._on_message(None, None, msg)

        callback.assert_not_called()


def test_pending_updates_discards_oldest_when_not_ready(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Retain only the newest pre-ready telemetry events at the queue limit.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        caplog: Pytest log capture fixture.
    """
    monkeypatch.setattr(
        "vauxhall.dashboard.app.settings.dashboard.pending_update_limit", 3
    )
    dashboard = DashboardApp(MagicMock())
    dashboard.window = MagicMock()
    dashboard.ipc.is_ready = False

    for sequence in range(1, 6):
        dashboard.on_telemetry(valid_event(details={"sequence": sequence}))

    assert [event["details"]["sequence"] for event in dashboard.pending_updates] == [
        3,
        4,
        5,
    ]
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING"
    ]
    assert len(warnings) == 2
    assert all(
        "discarded oldest pending telemetry update" in warning.lower()
        for warning in warnings
    )
    assert all("sequence" not in warning for warning in warnings)


def test_pending_updates_retains_configured_tail_of_ten_thousand_events(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep a bounded newest tail during a large pre-ready telemetry burst.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        caplog: Pytest log capture fixture.
    """
    monkeypatch.setattr(
        "vauxhall.dashboard.app.settings.dashboard.pending_update_limit", 3
    )
    dashboard = DashboardApp(MagicMock())
    dashboard.window = MagicMock()
    dashboard.ipc.is_ready = False

    for sequence in range(1, 10_001):
        dashboard.on_telemetry(valid_event(details={"sequence": sequence}))

    assert len(dashboard.pending_updates) == 3
    assert [event["details"]["sequence"] for event in dashboard.pending_updates] == [
        9_998,
        9_999,
        10_000,
    ]
    assert dashboard.discarded_pending_updates == 9_997
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert [record.args[0] for record in warnings] == [2**i for i in range(14)]


def test_readiness_transition_cannot_strand_a_pending_update() -> None:
    """An event racing frontend readiness must be delivered exactly once."""
    dashboard = DashboardApp(MagicMock())
    dashboard.window = MagicMock()
    readiness_read = Event()
    continue_read = Event()
    readiness_started = Event()
    original_ready_callback = dashboard.ipc.on_ready_callback

    class CoordinatedIPC:
        """Stub IPC that blocks the first readiness read until the test releases it."""

        def __init__(self) -> None:
            """Start out not ready."""
            self._is_ready = False

        @property
        def is_ready(self) -> bool:
            """Report readiness, pausing the first read that observes not ready.

            Returns:
                Whether the frontend is ready.

            Raises:
                TimeoutError: If the test does not release the read in time.
            """
            observed = self._is_ready
            if not observed:
                readiness_read.set()
                if not continue_read.wait(timeout=2):
                    raise TimeoutError
            return observed

        @is_ready.setter
        def is_ready(self, value: bool) -> None:
            """Set readiness.

            Args:
                value: Whether the frontend is ready.
            """
            self._is_ready = value

        def set_ready(self) -> bool:
            """Become ready and run the real readiness callback.

            Returns:
                Always ``True``.
            """
            self._is_ready = True
            readiness_started.set()
            assert original_ready_callback is not None
            original_ready_callback()
            return True

    dashboard.ipc = CoordinatedIPC()  # type: ignore[assignment]
    telemetry_thread = Thread(target=dashboard.on_telemetry, args=(valid_event(),))
    ready_thread = Thread(target=dashboard.ipc.set_ready)

    telemetry_thread.start()
    assert readiness_read.wait(timeout=2)
    ready_thread.start()
    assert readiness_started.wait(timeout=2)
    continue_read.set()
    telemetry_thread.join(timeout=2)
    ready_thread.join(timeout=2)

    assert not telemetry_thread.is_alive()
    assert not ready_thread.is_alive()
    assert not dashboard.pending_updates
    dashboard.window.invoke.assert_called_once_with("agent-update", valid_event())


def test_readiness_flush_delivers_queued_update_before_newer_live_update() -> None:
    """A live update cannot overtake the queued readiness snapshot."""
    dashboard = DashboardApp(MagicMock())
    queued_event = valid_event(state="Thinking")
    live_event = valid_event(state="Acting")
    dashboard.on_telemetry(queued_event)
    queued_dispatch_started = Event()
    continue_queued_dispatch = Event()
    live_saw_ready = Event()
    deliveries: list[str] = []
    original_ready_callback = dashboard.ipc.on_ready_callback

    class ReadinessObservingIPC:
        """Stub IPC that signals when a caller observes the ready state."""

        def __init__(self) -> None:
            """Start out not ready."""
            self._is_ready = False

        @property
        def is_ready(self) -> bool:
            """Report readiness, signalling when a caller observes it as ready.

            Returns:
                Whether the frontend is ready.
            """
            if self._is_ready:
                live_saw_ready.set()
            return self._is_ready

        @is_ready.setter
        def is_ready(self, value: bool) -> None:
            """Set readiness.

            Args:
                value: Whether the frontend is ready.
            """
            self._is_ready = value

        def set_ready(self) -> bool:
            """Run the real readiness callback, then become ready.

            Returns:
                Always ``True``.
            """
            assert original_ready_callback is not None
            original_ready_callback()
            if not self._is_ready:
                self._is_ready = True
            return True

    def invoke(_channel: str, event: dict[str, object]) -> None:
        """Record each delivery, holding the queued one until the test releases it.

        Args:
            event: The telemetry event being delivered.

        Raises:
            TimeoutError: If the test does not release the queued delivery in time.
        """
        if event["state"] == "Thinking":
            queued_dispatch_started.set()
            if not continue_queued_dispatch.wait(timeout=2):
                raise TimeoutError
        deliveries.append(str(event["state"]))

    dashboard.ipc = ReadinessObservingIPC()  # type: ignore[assignment]
    dashboard.window = MagicMock()
    dashboard.window.invoke.side_effect = invoke
    ready_thread = Thread(target=dashboard.ipc.set_ready)
    live_thread = Thread(target=dashboard.on_telemetry, args=(live_event,))

    ready_thread.start()
    assert queued_dispatch_started.wait(timeout=2)
    live_thread.start()
    assert live_saw_ready.wait(timeout=2)
    continue_queued_dispatch.set()
    ready_thread.join(timeout=2)
    live_thread.join(timeout=2)

    assert not ready_thread.is_alive()
    assert not live_thread.is_alive()
    assert deliveries == ["Thinking", "Acting"]


@patch("vauxhall.dashboard.app.pyloid_serve", return_value="http://localhost")
def test_dashboard_stops_mqtt_when_ui_loop_raises(mock_serve: MagicMock) -> None:
    """MQTT cleanup runs even when the UI event loop exits exceptionally.

    Args:
        mock_serve: Mock replacing ``vauxhall.dashboard.app.pyloid_serve``.
    """
    app = MagicMock()
    app.run.side_effect = RuntimeError("UI failed")

    with (
        patch("vauxhall.dashboard.app.DashboardSubscriber") as subscriber_type,
        pytest.raises(RuntimeError, match="UI failed"),
    ):
        DashboardApp(app).run()

    mock_serve.assert_called_once()
    subscriber_type.return_value.start.assert_called_once_with()
    subscriber_type.return_value.stop.assert_called_once_with()


@patch("vauxhall.dashboard.app.pyloid_serve", return_value="http://localhost")
def test_shutdown_status_is_not_sent_to_closed_window(mock_serve: MagicMock) -> None:
    """Status reported while stopping MQTT must not reach the destroyed window.

    Args:
        mock_serve: Mock replacing ``vauxhall.dashboard.app.pyloid_serve``.
    """
    app = MagicMock()
    dashboard = DashboardApp(app)

    def close_ready_window() -> None:
        """Mark the window ready, then end the UI loop as a close would.

        Raises:
            SystemExit: Always, standing in for the UI loop exiting.
        """
        dashboard.ipc.is_ready = True
        raise SystemExit(0)

    app.run.side_effect = close_ready_window

    with patch("vauxhall.dashboard.app.DashboardSubscriber") as subscriber_type:
        subscriber_type.return_value.stop.side_effect = lambda: dashboard.on_status(
            "Disconnected"
        )
        with pytest.raises(SystemExit):
            dashboard.run()

    mock_serve.assert_called_once()
    subscriber_type.return_value.stop.assert_called_once_with()
    app.create_window.return_value.invoke.assert_not_called()
    assert dashboard.last_status == "Disconnected"


if __name__ == "__main__":
    unittest.main()
