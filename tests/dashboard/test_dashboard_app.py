# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for Vauxhall Dashboard components."""

import unittest
from copy import deepcopy
from typing import Any
from unittest.mock import ANY, MagicMock, call, patch

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

from vauxhall.dashboard.app import (  # noqa: E402
    ICON_FILE,
    DashboardApp,
    WindowEvent,
    _set_chromium_flags,
)


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


def run_now(handler: WindowEvent) -> WindowEvent:
    """Stand in for the UI-thread queue by running each event at once.

    Args:
        handler: The dashboard's window-event handler.

    Returns:
        The handler itself.
    """
    return handler


class DeferredQueue:
    """Stand in for the UI-thread queue, holding events until ``run``."""

    def __init__(self) -> None:
        """Start with nothing queued."""
        self.handler: WindowEvent | None = None
        self.queued: list[tuple[str, object]] = []
        self.posted: list[str] = []

    def wrap(self, handler: WindowEvent) -> WindowEvent:
        """Keep the dashboard's handler and return a poster that queues.

        Args:
            handler: The dashboard's window-event handler.

        Returns:
            A poster that records each event without running it.
        """
        self.handler = handler
        return self.post

    def post(self, name: str, data: object) -> None:
        """Queue one event.

        Args:
            name: The window event name.
            data: The event payload.
        """
        self.posted.append(name)
        self.queued.append((name, data))

    def run(self) -> None:
        """Run the queued events in order, as the UI thread would."""
        assert self.handler is not None
        while self.queued:
            self.handler(*self.queued.pop(0))


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
        self.dashboard = DashboardApp(self.mock_app, queue_to_ui=run_now)
        self.dashboard.window = MagicMock()

    def test_ipc_notify_shows_a_system_tray_notification(self) -> None:
        """The IPC bridge's notify call reaches the Pyloid app's tray notification."""
        assert (
            self.dashboard.ipc.notify("Codex needs attention", "Prompt: continue?")
            is True
        )

        self.mock_app.show_notification.assert_called_once_with(
            "Codex needs attention", "Prompt: continue?"
        )

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
        """Telemetry is queued until the frontend is ready, then flushed."""
        self.dashboard.ipc.is_ready = False

        valid_data = self.valid_telemetry()
        self.dashboard.on_telemetry(valid_data)

        # Should be queued, not invoked
        self.dashboard.window.invoke.assert_not_called()
        assert len(self.dashboard.pending_updates) == 1
        assert self.dashboard.pending_updates[0] == valid_data

        self.dashboard.ipc.set_ready()
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

    def test_on_telemetry_drops_denylisted_agent(self) -> None:
        """Telemetry for a denylisted agent is dropped, not queued or forwarded."""
        self.dashboard.ipc.is_ready = True
        with patch(
            "vauxhall.dashboard.app.settings.dashboard.agent_denylist", ["TestAgent"]
        ):
            self.dashboard.on_telemetry(self.valid_telemetry())

        self.dashboard.window.invoke.assert_not_called()
        assert not self.dashboard.pending_updates

    def test_on_telemetry_drops_denylisted_agent_while_not_ready(self) -> None:
        """A denylisted agent's telemetry is not queued for a later drain."""
        self.dashboard.ipc.is_ready = False
        with patch(
            "vauxhall.dashboard.app.settings.dashboard.agent_denylist", ["TestAgent"]
        ):
            self.dashboard.on_telemetry(self.valid_telemetry())

        assert not self.dashboard.pending_updates

    def test_on_telemetry_allows_agents_not_on_the_denylist(self) -> None:
        """Telemetry for an agent not on the denylist is forwarded as usual."""
        self.dashboard.ipc.is_ready = True
        valid_data = self.valid_telemetry()
        with patch(
            "vauxhall.dashboard.app.settings.dashboard.agent_denylist", ["OtherAgent"]
        ):
            self.dashboard.on_telemetry(valid_data)

        self.dashboard.window.invoke.assert_called_once_with("agent-update", valid_data)

    def test_on_telemetry_rechecks_denylist_on_the_ui_thread(self) -> None:
        """A denylist save landing after telemetry is posted still drops it."""
        queue = DeferredQueue()
        dashboard = DashboardApp(self.mock_app, queue_to_ui=queue.wrap)
        dashboard.window = MagicMock()
        dashboard.ipc.is_ready = True
        denylist: list[str] = []

        with patch(
            "vauxhall.dashboard.app.settings.dashboard.agent_denylist", denylist
        ):
            dashboard.on_telemetry(self.valid_telemetry())
            denylist.append("TestAgent")
            queue.run()

        assert queue.posted == ["agent-update"]
        dashboard.window.invoke.assert_not_called()


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
    dashboard = DashboardApp(MagicMock(), queue_to_ui=run_now)
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
    dashboard = DashboardApp(MagicMock(), queue_to_ui=run_now)
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


def test_update_posted_before_readiness_but_run_after_it_is_sent_once() -> None:
    """Telemetry still queued when the frontend becomes ready follows the backlog."""
    queue = DeferredQueue()
    dashboard = DashboardApp(MagicMock(), queue_to_ui=queue.wrap)
    dashboard.window = MagicMock()
    dashboard.on_telemetry(valid_event(session_id="held"))
    queue.run()
    dashboard.on_telemetry(valid_event(session_id="in-flight"))

    dashboard.ipc.set_ready()
    queue.run()

    assert not dashboard.pending_updates
    sent = [
        sent.args[1]["session_id"] for sent in dashboard.window.invoke.call_args_list
    ]
    assert sent == ["held", "in-flight"]


def test_events_still_queued_at_shutdown_are_not_sent_to_the_closed_window() -> None:
    """Shutdown's own Pyloid calls can run queued events; they must be dropped.

    Sending one to the deleted web view makes Pyloid wait forever for a result.
    """
    queue = DeferredQueue()
    dashboard = DashboardApp(MagicMock(), queue_to_ui=queue.wrap)
    dashboard.window = MagicMock()
    dashboard.ipc.is_ready = True
    dashboard.on_telemetry(valid_event())
    dashboard.on_status("Connected to Agent Fleet")

    dashboard.ipc.is_ready = False
    queue.run()

    assert queue.posted == ["agent-update", "status-update"]
    dashboard.window.invoke.assert_not_called()


def test_readiness_posts_the_last_status_before_queued_updates() -> None:
    """A ready frontend gets the connection status, then the queued updates."""
    queue = DeferredQueue()
    dashboard = DashboardApp(MagicMock(), queue_to_ui=queue.wrap)
    dashboard.window = MagicMock()
    dashboard.on_status("Connecting...")
    dashboard.on_telemetry(valid_event())
    dashboard.on_status("Connected to Agent Fleet")
    queue.run()
    dashboard.window.invoke.assert_not_called()

    dashboard.ipc.set_ready()

    assert dashboard.window.invoke.call_args_list == [
        call("status-update", "Connected to Agent Fleet"),
        call("agent-update", valid_event()),
    ]


def test_events_run_by_a_nested_event_loop_wait_for_the_outbox() -> None:
    """An update run inside invoke() is sent after the backlog, not nested in it.

    Pyloid's invoke() waits for its result in a nested event loop, which runs
    the next posted event before invoke() returns. Nesting a send per event
    would deepen the stack with every event in a flood.
    """
    queue = DeferredQueue()
    dashboard = DashboardApp(MagicMock(), queue_to_ui=queue.wrap)
    dashboard.window = MagicMock()
    dashboard.on_telemetry(valid_event(session_id="queued-1"))
    dashboard.on_telemetry(valid_event(session_id="queued-2"))
    queue.run()
    dashboard.on_telemetry(valid_event(session_id="live"))
    depth = 0
    deepest = 0

    def invoke_with_nested_loop(_name: str, _data: object) -> None:
        """Run posted events while this send is in progress, as Pyloid does.

        Args:
            _name: The window event name.
            _data: The event payload.
        """
        nonlocal depth, deepest
        depth += 1
        deepest = max(deepest, depth)
        queue.run()
        depth -= 1

    dashboard.window.invoke.side_effect = invoke_with_nested_loop

    dashboard.ipc.set_ready()

    sent = [
        sent.args[1]["session_id"] for sent in dashboard.window.invoke.call_args_list
    ]
    assert sent == ["queued-1", "queued-2", "live"]
    assert deepest == 1


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
    dashboard = DashboardApp(app, queue_to_ui=run_now)

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


@pytest.mark.parametrize(
    ("user_flags", "expected"),
    [
        ("", "--enable-features=X"),
        ("--disable-gpu", "--enable-features=X --disable-gpu"),
        (
            "--ignore-certificate-errors",
            "--enable-features=X --ignore-certificate-errors",
        ),
    ],
    ids=["unset", "set", "user-chosen-override"],
)
def test_set_chromium_flags_drops_pyloids_certificate_overrides(
    user_flags: str, expected: str
) -> None:
    """Pyloid's certificate overrides go; the user's flags are kept as given.

    Args:
        user_flags: The flags the user set before Pyloid's import.
        expected: The resulting flags.
    """
    environ = {
        "QTWEBENGINE_CHROMIUM_FLAGS": "--enable-features=X "
        "--ignore-certificate-errors --allow-insecure-localhost"
    }

    _set_chromium_flags(environ, user_flags)

    assert environ == {"QTWEBENGINE_CHROMIUM_FLAGS": expected}


if __name__ == "__main__":
    unittest.main()
