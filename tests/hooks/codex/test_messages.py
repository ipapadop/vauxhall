# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for reading interim Codex messages from the session record."""

import json
import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

from vauxhall.hooks.codex import messages


def _commentary(text: str) -> str:
    """Return one session record line holding completed commentary.

    Args:
        text: The commentary text.

    Returns:
        The JSON line, newline included.
    """
    record = {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "turn_id": "turn-1",
            "item": {"type": "AgentMessage", "phase": "commentary", "content": text},
        },
    }
    return json.dumps(record) + "\n"


def _event(transcript: Path, name: str = "PreToolUse") -> dict[str, str]:
    """Return a Codex hook event naming a session record.

    Args:
        transcript: The session record.
        name: The hook event name.

    Returns:
        The event.
    """
    return {
        "hook_event_name": name,
        "session_id": "session-1",
        "turn_id": "turn-1",
        "transcript_path": str(transcript),
    }


def _during_first_parse(
    action: Callable[[], None],
) -> AbstractContextManager[object]:
    """Patch the record parser to run an action once, mid-read.

    The parser runs after the cursor is read and before it is written, so the
    action stands in for a second hook process running in between.

    Args:
        action: What the concurrent hook process does.

    Returns:
        The patch, to use as a context manager.
    """
    parse = messages._commentary_text
    pending = [action]

    def parse_after_action(line: bytes, turn_id: str) -> str | None:
        while pending:
            pending.pop()()
        return parse(line, turn_id)

    return patch.object(messages, "_commentary_text", parse_after_action)


def test_concurrent_events_report_each_message_once(tmp_path: Path) -> None:
    """An event running while another reads neither repeats nor rewinds.

    Args:
        tmp_path: Pytest temporary directory.
    """
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text("", encoding="utf-8")
    messages.new_messages(_event(transcript, "UserPromptSubmit"))
    transcript.write_text(_commentary("first"), encoding="utf-8")
    reported: list[str] = []

    def concurrent_event() -> None:
        with transcript.open("a", encoding="utf-8") as output:
            output.write(_commentary("second"))
        reported.extend(messages.new_messages(_event(transcript)))

    with _during_first_parse(concurrent_event):
        reported.extend(messages.new_messages(_event(transcript)))
    reported.extend(messages.new_messages(_event(transcript)))

    assert sorted(reported) == ["first", "second"]


def _cursor_directory(tempdir: Path) -> Path:
    """Return the Codex cursor directory.

    Args:
        tempdir: The directory standing in for the system temporary directory.

    Returns:
        The directory.
    """
    (directory,) = tempdir.glob("vauxhall-codex-cursors*")
    return directory


def _cursor_files(tempdir: Path) -> list[str]:
    """Return the names of the files in the Codex cursor directory.

    Args:
        tempdir: The directory standing in for the system temporary directory.

    Returns:
        The sorted file names.
    """
    return sorted(path.name for path in _cursor_directory(tempdir).iterdir())


def test_event_before_any_cursor_reports_nothing(
    tmp_path: Path, isolated_tempdir: Path
) -> None:
    """Without a cursor from UserPromptSubmit, records are not guessed at.

    Args:
        tmp_path: Pytest temporary directory.
        isolated_tempdir: The directory standing in for the system one.
    """
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text(_commentary("first"), encoding="utf-8")

    assert messages.new_messages(_event(transcript)) == []
    assert _cursor_files(isolated_tempdir) == []


def test_failed_read_puts_the_claimed_cursor_back(
    tmp_path: Path, isolated_tempdir: Path
) -> None:
    """A session record that can't be read leaves the cursor for the next event.

    Args:
        tmp_path: Pytest temporary directory.
        isolated_tempdir: The directory standing in for the system one.
    """
    transcript = tmp_path / "rollout"
    transcript.mkdir()
    messages.new_messages(_event(transcript, "UserPromptSubmit"))
    (cursor,) = _cursor_files(isolated_tempdir)

    assert messages.new_messages(_event(transcript)) == []
    assert _cursor_files(isolated_tempdir) == [cursor]


def test_claims_left_by_a_dead_hook_are_swept(
    tmp_path: Path, isolated_tempdir: Path
) -> None:
    """A claimed cursor older than a day is removed on the next prompt.

    Args:
        tmp_path: Pytest temporary directory.
        isolated_tempdir: The directory standing in for the system one.
    """
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text("", encoding="utf-8")
    messages.new_messages(_event(transcript, "UserPromptSubmit"))
    (cursor,) = _cursor_files(isolated_tempdir)
    leftover = (
        _cursor_directory(isolated_tempdir) / f"{'0' * 64}.0123456789abcdef.claimed"
    )
    leftover.write_text("0", encoding="ascii")
    day_ago = time.time() - 25 * 60 * 60
    os.utime(leftover, (day_ago, day_ago))

    messages.new_messages(_event(transcript, "UserPromptSubmit"))

    assert _cursor_files(isolated_tempdir) == [cursor]
