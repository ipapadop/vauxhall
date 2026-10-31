# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for running one hook process."""

import importlib
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from vauxhall.core.telemetry import MAX_DETAIL_STRING_LENGTH, MAX_WORKSPACE_LENGTH
from vauxhall.hooks import runner
from vauxhall.hooks.claude import telemetry_hook as claude_hook
from vauxhall.hooks.client import format_message

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

    runner.publish_telemetry(
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


@pytest.mark.parametrize(
    ("event", "key"),
    [
        ({"hook_event_name": "UserPromptSubmit", "prompt": "p" * 5000}, "prompt"),
        (
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "c" * 5000},
            },
            "cmd",
        ),
    ],
)
def test_publish_telemetry_truncates_a_detail_too_long_to_publish(
    event: dict[str, Any], key: str
) -> None:
    """A long prompt or command is shortened instead of dropping the event.

    Args:
        event: The hook event carrying the long value.
        key: The detail holding it.
    """
    publisher = RecordingPublisher()

    runner.publish_telemetry(
        {**event, "session_id": "one", "cwd": "/workspace"},
        "Claude",
        claude_hook.HANDLERS,
        publish=publisher,
    )

    [[payload]] = publisher.batches
    value = payload["details"][key]
    assert len(value) == MAX_DETAIL_STRING_LENGTH
    assert value.endswith("…")
    format_message(payload)


def test_publish_telemetry_shortens_a_workspace_too_long_to_publish() -> None:
    """A long workspace is shortened instead of dropping the event.

    Two long workspaces that differ only in the middle keep separate cards.
    """
    publisher = RecordingPublisher()
    workspaces = [f"/home/user/{'a' * 3000}{middle}{'b' * 3000}" for middle in "xy"]

    for workspace in workspaces:
        runner.publish_telemetry(
            {"hook_event_name": "Stop", "session_id": "one", "cwd": workspace},
            "Claude",
            claude_hook.HANDLERS,
            publish=publisher,
        )

    published = [payload["workspace"] for [payload] in publisher.batches]
    assert len(published) == 2
    assert published[0] != published[1]
    for value in published:
        assert len(value) <= MAX_WORKSPACE_LENGTH
        assert value.startswith("/home/user/aaa")
    format_message(publisher.batches[0][0])


def _deleted_directory() -> Path:
    """Stand in for ``Path.cwd`` in a deleted directory.

    Raises:
        FileNotFoundError: Always.
    """
    raise FileNotFoundError


def test_event_workspace_uses_the_cwd_without_asking_the_process() -> None:
    """A deleted hook working directory doesn't matter when the event has one."""
    assert runner.event_workspace({"cwd": "/workspace"}, _deleted_directory) == (
        "/workspace"
    )


@pytest.mark.parametrize("cwd", ["", "   ", None, 42])
def test_event_workspace_falls_back_to_the_process_directory(cwd: object) -> None:
    """A missing, blank, or non-string ``cwd`` falls back to the process's.

    Args:
        cwd: The unusable ``cwd`` value.
    """
    fallback = Path("/fallback")

    assert runner.event_workspace({"cwd": cwd}, lambda: fallback) == str(fallback)


def test_event_workspace_is_none_without_any_directory() -> None:
    """No ``cwd`` and no process directory leaves nothing to key a card by."""
    assert runner.event_workspace({}, _deleted_directory) is None


def test_publish_telemetry_keeps_an_event_with_a_blank_cwd() -> None:
    """A blank ``cwd`` is published as the process directory, not dropped."""
    publisher = RecordingPublisher()

    runner.publish_telemetry(
        {"hook_event_name": "Stop", "session_id": "one", "cwd": ""},
        "Claude",
        claude_hook.HANDLERS,
        publish=publisher,
    )

    [[payload]] = publisher.batches
    assert payload["workspace"] == str(Path.cwd())
    format_message(payload)


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
def test_hook_import_leaves_out_slow_modules(hook: str) -> None:
    """An agent waits for every hook, so importing one loads no slow module.

    The installer and the MQTT client are imported only when needed.

    Args:
        hook: The hook module.
    """
    slow = ["subprocess", "paho", "vauxhall.hooks.installation"]
    script = f"import sys, {hook}; print([m for m in {slow!r} if m in sys.modules])"

    completed = subprocess.run(
        [sys.executable, "-P", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == "[]\n"


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
def test_hook_warns_about_a_workspace_hooks_file(tmp_path: Path, hook: str) -> None:
    """A hook names the workspace file it ignores, and stdout stays valid.

    Args:
        tmp_path: Pytest temporary directory, the hook's workspace.
        hook: The hook module.
    """
    (tmp_path / "vauxhall_hooks.json").write_text('{"mqtt": {"host": "x.example"}}')
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VAUXHALL_")
    }
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
    assert completed.stderr.count("Ignoring ") == 1


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
