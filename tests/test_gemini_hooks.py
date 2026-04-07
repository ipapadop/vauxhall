"""Tests for Gemini CLI hooks."""

from unittest.mock import MagicMock, patch

from vauxhall.hooks.gemini.post_command import main as post_main
from vauxhall.hooks.gemini.pre_command import main as pre_main


def test_pre_command_sends_telemetry() -> None:
    """Verify that pre_command correctly sends Acting state telemetry."""
    with (
        patch("vauxhall.hooks.gemini.pre_command.TelemetryClient") as MockClient,
        patch("sys.argv", ["script.py", "grep", "pattern"]),
        patch("os.getcwd", return_value="/workspace"),
    ):
        mock_instance: MagicMock = MockClient.return_value
        pre_main()

        mock_instance.send.assert_called_once_with(
            "Gemini", "/workspace", "Acting", tool="command", cmd="grep pattern"
        )


def test_post_command_sends_telemetry() -> None:
    """Verify that post_command correctly sends Idle state telemetry."""
    with (
        patch("vauxhall.hooks.gemini.post_command.TelemetryClient") as MockClient,
        patch("os.getcwd", return_value="/workspace"),
    ):
        mock_instance: MagicMock = MockClient.return_value
        post_main()

        mock_instance.send.assert_called_once_with("Gemini", "/workspace", "Idle")
