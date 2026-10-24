# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the runtime helpers shared by the built-in hooks."""

import importlib
import json
import os
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from vauxhall.hooks import common
from vauxhall.hooks.panes import PaneTarget, load_pane, record_pane

IDENTITY = ["session-123", "call-123"]
HOOKS = [
    pytest.param("vauxhall.hooks.claude.telemetry_hook", id="claude"),
    pytest.param("vauxhall.hooks.codex.telemetry_hook", id="codex"),
    pytest.param("vauxhall.hooks.gemini.telemetry_hook", id="gemini"),
]
SESSION_START = {
    "hook_event_name": "SessionStart",
    "source": "startup",
    "session_id": "session-123",
    "cwd": "/workspace",
}
UNREACHABLE_BROKER = {"VAUXHALL_MQTT_HOST": "127.0.0.1", "VAUXHALL_MQTT_PORT": "1"}


def test_claim_skips_start_claimed_by_another_hook(tmp_path: Path) -> None:
    """A start renamed away by a concurrent hook must not be claimed twice.

    Args:
        tmp_path: Pytest temporary directory.
    """
    real_rename = Path.rename
    lost_races: list[Path] = []

    def rename_after_losing_first_race(path: Path, target: Path) -> Path:
        """Fail the first rename as a competing hook would, then behave normally.

        Args:
            path: The start file being claimed.
            target: Name the claimed file is given.

        Returns:
            The renamed path.

        Raises:
            FileNotFoundError: On the first call, as a lost race would.
        """
        if not lost_races:
            lost_races.append(path)
            path.unlink()
            raise FileNotFoundError(path)
        return real_rename(path, target)

    with (
        patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(common.time, "time", side_effect=[1000.0, 1004.0, 1010.0]),
    ):
        common.record_tool_start("test", IDENTITY)
        common.record_tool_start("test", IDENTITY)
        with patch.object(Path, "rename", rename_after_losing_first_race):
            duration = common.claim_tool_duration("test", IDENTITY)

    assert duration == 10.0
    assert len(lost_races) == 1
    assert not list(tmp_path.rglob("*.time"))
    assert not list(tmp_path.rglob("*.claimed"))


def test_claim_discards_unreadable_start(tmp_path: Path) -> None:
    """A start file that cannot be parsed is removed and the next one is used.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with (
        patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(common.time, "time", side_effect=[1000.0, 1004.0, 1010.0]),
    ):
        common.record_tool_start("test", IDENTITY)
        common.record_tool_start("test", IDENTITY)
        newest = max(tmp_path.rglob("*.time"))
        newest.write_text("not a time")
        duration = common.claim_tool_duration("test", IDENTITY)

    assert duration == 10.0
    assert not list(tmp_path.rglob("*.time"))
    assert not list(tmp_path.rglob("*.claimed"))


def test_private_directory_allows_a_platform_without_posix_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A platform that reports no owner and no mode bits must still be usable.

    Windows ignores the mode a directory is created with, reports every
    directory as world accessible, and has no ``os.getuid``.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setattr(common.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.delattr(common.os, "getuid", raising=False)
    directory = tmp_path / f"vauxhall-messages-claude{common._USER_SUFFIX}"
    directory.mkdir()
    directory.chmod(0o777)

    assert common.private_directory("vauxhall-messages-claude") == directory


def test_collect_message_chunks_returns_one_bounded_message(tmp_path: Path) -> None:
    """Streaming text is kept private and published once per completed message.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        assert (
            common.collect_message_chunk(
                "claude", ["session", "message"], "Hello ", final=False
            )
            is None
        )
        assert (
            common.collect_message_chunk(
                "claude", ["session", "other"], "Other", final=True
            )
            == "Other"
        )
        assert (
            common.collect_message_chunk(
                "claude", ["session", "message"], "world", final=True
            )
            == "Hello world"
        )

    assert not list(tmp_path.rglob("*.message"))


def test_collect_message_chunks_caps_long_text(tmp_path: Path) -> None:
    """A long reply fits the telemetry detail string limit.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        message = common.collect_message_chunk(
            "gemini", ["session"], "x" * 5000, final=True
        )

    assert message == "x" * 4095 + "…"


def test_discard_message_chunks_prevents_next_turn_contamination(
    tmp_path: Path,
) -> None:
    """An unfinished response is cleared before a new turn begins.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        common.collect_message_chunk("gemini", ["session"], "old", final=False)
        common.discard_message_chunks("gemini", ["session"])
        message = common.collect_message_chunk("gemini", ["session"], "new", final=True)

    assert message == "new"


def test_collect_message_chunk_sweeps_text_of_long_abandoned_responses(
    tmp_path: Path,
) -> None:
    """Text of a response unfinished for over a day is removed on the next chunk.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        common.collect_message_chunk("codex", ["old"], "old", final=False)
        common.collect_message_chunk("codex", ["recent"], "recent", final=False)
        old, recent = sorted(
            tmp_path.rglob("*.message"), key=lambda path: path.read_text()
        )
        day_ago = time.time() - 25 * 60 * 60
        os.utime(old, (day_ago, day_ago))

        common.collect_message_chunk("codex", ["new"], "new", final=False)

    assert not old.exists()
    assert recent.exists()


@pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="Windows has no mode bits to plant, and its temporary directory is "
    "per account",
)
def test_private_directory_rejects_a_directory_another_account_could_reach(
    tmp_path: Path,
) -> None:
    """A pre-created world-writable directory is refused, not reused.

    Args:
        tmp_path: Pytest temporary directory.
    """
    planted = tmp_path / f"vauxhall-messages-claude{common._USER_SUFFIX}"
    planted.mkdir()
    planted.chmod(0o777)

    with (
        patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)),
        pytest.raises(OSError, match="not a private directory"),
    ):
        common.private_directory("vauxhall-messages-claude")


def test_collect_message_chunk_writes_nothing_through_a_planted_symlink(
    tmp_path: Path,
) -> None:
    """Assistant text never reaches a directory another account redirected.

    Args:
        tmp_path: Pytest temporary directory.
    """
    suffix = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
    elsewhere = tmp_path / "attacker"
    elsewhere.mkdir()
    (tmp_path / f"vauxhall-messages-claude{suffix}").symlink_to(elsewhere)

    with patch.object(common.tempfile, "gettempdir", return_value=str(tmp_path)):
        message = common.collect_message_chunk("claude", ["s"], "secret", final=True)

    assert message is None
    assert not list(elsewhere.iterdir())


class RecordingPublisher:
    """Stands in for the telemetry publisher, recording each batch."""

    def __init__(self) -> None:
        """Create a publisher that has published nothing."""
        self.batches: list[list[dict[str, Any]]] = []

    def __call__(self, events: list[dict[str, Any]]) -> bool:
        """Record one batch.

        Args:
            events: The events published together.

        Returns:
            Always ``True``.
        """
        self.batches.append(events)
        return True


def test_publish_telemetry_sends_messages_and_event_in_one_batch() -> None:
    """Interim messages and the event go out together, in the wire shape."""
    publisher = RecordingPublisher()

    common.publish_telemetry(
        {"hook_event_name": "Stop", "session_id": "one", "cwd": "/workspace"},
        "Codex",
        {"Stop": lambda _: ("Idle", {"status": "done"})},
        publish=publisher,
        messages=["first", "second"],
    )

    identity = {"agent": "Codex", "workspace": "/workspace", "session_id": "native:one"}
    assert publisher.batches == [
        [
            {**identity, "state": "Thinking", "details": {"message": "first"}},
            {**identity, "state": "Thinking", "details": {"message": "second"}},
            {**identity, "state": "Idle", "details": {"status": "done"}},
        ]
    ]


def test_publish_telemetry_records_the_pane_at_session_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session that starts in tmux becomes reachable for dashboard prompts.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("TMUX_PANE", "%5")
    monkeypatch.delenv("TMUX", raising=False)

    common.publish_telemetry(
        {"hook_event_name": "SessionStart", "session_id": "one", "source": "startup"},
        "Codex",
        {"SessionStart": common.session_start_telemetry},
        publish=RecordingPublisher(),
    )

    assert load_pane("codex", "native:one") == PaneTarget("%5", None, None)


def test_track_pane_records_the_agent_command_at_session_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The relay can later tell the agent from a shell left in its pane.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("TMUX_PANE", "%5")

    common.track_pane("SessionStart", "Claude", "native:one", lambda: "claude")

    assert load_pane("claude", "native:one") == PaneTarget("%5", None, None, "claude")


def test_publish_telemetry_forgets_the_pane_at_session_end() -> None:
    """A session that ended can no longer be sent prompts."""
    record_pane("codex", "native:one", {"TMUX_PANE": "%5"})

    common.publish_telemetry(
        {"hook_event_name": "SessionEnd", "session_id": "one"},
        "Codex",
        {"SessionEnd": lambda _: ("Idle", {"status": "session ended"})},
        publish=RecordingPublisher(),
    )

    assert load_pane("codex", "native:one") is None


def test_pane_record_failure_never_disturbs_the_hook(
    isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable record is ignored and telemetry still goes out.

    Args:
        isolated_home: The temporary home directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("TMUX_PANE", "%5")
    # A file where the records directory belongs makes writing fail for real.
    (isolated_home / ".config" / "vauxhall").mkdir(parents=True)
    (isolated_home / ".config" / "vauxhall" / "panes").write_text("", encoding="utf-8")
    publisher = RecordingPublisher()

    common.publish_telemetry(
        {"hook_event_name": "SessionStart", "session_id": "one"},
        "Codex",
        {"SessionStart": common.session_start_telemetry},
        publish=publisher,
    )

    assert len(publisher.batches) == 1


def _run_main(hook: str, stdin: str) -> str:
    """Run a hook's ``main`` in process and return what it wrote to stdout.

    Args:
        hook: The hook module.
        stdin: The hook's standard input.

    Returns:
        The hook's standard output.
    """
    output = StringIO()
    with patch("sys.stdin", StringIO(stdin)), patch("sys.stdout", output):
        importlib.import_module(hook).main()
    return output.getvalue()


def _run_process(
    hook: str, stdin: str, environment: dict[str, str] | None = None, **options: object
) -> subprocess.CompletedProcess[str]:
    """Run a hook module as its own process, the way an agent does.

    Args:
        hook: The hook module.
        stdin: The hook's standard input.
        environment: Variables added to the inherited environment.
        **options: Further ``subprocess.run`` options.

    Returns:
        The completed process.
    """
    return subprocess.run(
        [sys.executable, "-m", hook],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **UNREACHABLE_BROKER, **(environment or {})},
        **options,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("hook", HOOKS)
@pytest.mark.parametrize("stdin", ["not json", "[]"])
def test_hook_answers_input_it_cannot_use(hook: str, stdin: str) -> None:
    """Input that is not a JSON object still gets one JSON object back.

    Args:
        hook: The hook module.
        stdin: The case's standard input.
    """
    completed = _run_process(hook, stdin)

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"


@pytest.mark.parametrize("hook", HOOKS)
def test_hook_keeps_debug_logs_off_stdout(hook: str) -> None:
    """Debug logging goes to stderr, so stdout stays a valid hook response.

    Args:
        hook: The hook module.
    """
    completed = _run_process(
        hook, json.dumps(SESSION_START), {"VAUXHALL_LOGGING_LEVEL": "DEBUG"}
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert "Failed to connect telemetry client" in completed.stderr


@pytest.mark.parametrize("hook", HOOKS)
def test_hook_survives_telemetry_import_failure(hook: str) -> None:
    """A broken telemetry client import still produces the hook response.

    Args:
        hook: The hook module.
    """
    command = (
        "import importlib, sys; "
        "sys.modules['vauxhall.hooks.client'] = None; "
        f"importlib.import_module({hook!r}).main()"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        input=json.dumps(SESSION_START),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"


@pytest.mark.parametrize("hook", HOOKS)
@pytest.mark.parametrize(
    ("environment_value", "file_payload", "expected"),
    [
        ("invalid", None, ("VAUXHALL_MQTT_PORT", "'invalid'")),
        (None, {"mqtt": []}, ("vauxhall_hooks.json", "[]")),
    ],
)
def test_hook_reports_invalid_configuration_without_breaking_protocol(
    tmp_path: Path,
    hook: str,
    environment_value: str | None,
    file_payload: object | None,
    expected: tuple[str, str],
) -> None:
    """Invalid hook configuration is named on stderr and stdout stays valid.

    Args:
        tmp_path: Pytest temporary directory.
        hook: The hook module.
        environment_value: The case's environment variable value.
        file_payload: The case's file contents.
        expected: The source and the value the error must name.
    """
    if file_payload is not None:
        user_file = Path.home() / ".config" / "vauxhall" / "vauxhall_hooks.json"
        user_file.parent.mkdir(parents=True)
        user_file.write_text(json.dumps(file_payload))
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VAUXHALL_")
    }
    if environment_value is not None:
        environment["VAUXHALL_MQTT_PORT"] = environment_value
    project_root = str(Path(__file__).resolve().parents[2])
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (project_root, environment.get("PYTHONPATH")))
    )

    completed = subprocess.run(
        [sys.executable, "-m", hook],
        input="{}",
        text=True,
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == "{}\n"
    assert all(text in completed.stderr for text in expected)
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize("hook", HOOKS)
def test_hook_answers_when_telemetry_setup_fails(hook: str) -> None:
    """A telemetry client that cannot be created is invisible to the agent.

    Args:
        hook: The hook module.
    """
    with patch("vauxhall.hooks.client.publish", side_effect=RuntimeError):
        assert _run_main(hook, json.dumps(SESSION_START)) == "{}\n"


@pytest.mark.parametrize("hook", HOOKS)
def test_hook_skips_event_without_stable_session_identity(hook: str) -> None:
    """Without a session identity, nothing is published.

    Args:
        hook: The hook module.
    """
    event = {key: value for key, value in SESSION_START.items() if key != "session_id"}
    with patch("vauxhall.hooks.client.publish") as publish:
        assert _run_main(hook, json.dumps(event)) == "{}\n"

    publish.assert_not_called()
