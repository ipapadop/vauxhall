# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Best-effort interim Codex messages from the local session record."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from vauxhall.hooks.common import message_text, private_directory

_MAX_READ_BYTES = 1_048_576


def _cursor_path(session_id: str, transcript_path: str) -> Path:
    """Return a private cursor path for one Codex session record.

    Args:
        session_id: The Codex session the cursor belongs to.
        transcript_path: Path of the session record being read.

    Returns:
        The path holding the offset read so far.

    Raises:
        OSError: If the cursor directory is not a private one this user owns.
    """
    directory = private_directory("vauxhall-codex-cursors")
    key = hashlib.sha256(f"{session_id}\0{transcript_path}".encode()).hexdigest()
    return directory / key


def _write_cursor(path: Path, offset: int) -> None:
    """Save the last complete record offset for a later hook invocation.

    Args:
        path: The cursor file to write.
        offset: Byte offset of the first record not yet reported.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as output:
        output.write(str(offset))


def _commentary_text(line: bytes, turn_id: str) -> str | None:
    """Extract a displayed Codex commentary message from one session record.

    Args:
        line: One JSON record from the session file.
        turn_id: The turn whose commentary is wanted.

    Returns:
        The commentary text, or ``None`` when the record is not completed
        commentary from that turn.
    """
    try:
        record = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or record.get("type") != "event_msg":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "item_completed":
        return None
    item = payload.get("item")
    if (
        payload.get("turn_id") != turn_id
        or not isinstance(item, dict)
        or item.get("type") != "AgentMessage"
        or item.get("phase") != "commentary"
    ):
        return None
    return message_text(item.get("content"))


def new_messages(input_data: dict[str, Any]) -> list[str]:
    """Read new completed commentary from the current Codex turn, if possible.

    Reading is best effort: the record format can change, and Codex may write
    it after the hook runs, so a failure yields no messages rather than raising.

    Args:
        input_data: The hook event naming the session record and turn.

    Returns:
        The commentary completed since the last invocation, oldest first.
    """
    transcript_path = input_data.get("transcript_path")
    session_id = input_data.get("session_id")
    turn_id = input_data.get("turn_id")
    if not all(
        isinstance(value, str) and value
        for value in (transcript_path, session_id, turn_id)
    ):
        return []
    try:
        transcript = Path(transcript_path)
        size = transcript.stat().st_size
        cursor = _cursor_path(session_id, transcript_path)
        if input_data.get("hook_event_name") == "UserPromptSubmit":
            _write_cursor(cursor, size)
            return []
        if input_data.get("hook_event_name") not in {
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "Stop",
        }:
            return []
        try:
            saved = os.open(cursor, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(saved, encoding="ascii") as source:
                offset = int(source.read())
        except (OSError, ValueError):
            offset = 0
        if offset > size:
            offset = 0
        with transcript.open("rb") as source:
            source.seek(offset)
            data = source.read(_MAX_READ_BYTES)
        last_newline = data.rfind(b"\n")
        if last_newline == -1:
            # A record longer than one read has no usable line; skip past it so
            # the cursor still advances instead of re-reading the same bytes.
            complete = b""
            next_offset = offset + len(data)
        else:
            complete = data[:last_newline]
            next_offset = offset + last_newline + 1
        messages = [
            message
            for line in complete.splitlines()
            if (message := _commentary_text(line, turn_id)) is not None
        ]
        _write_cursor(cursor, next_offset)
    except (OSError, ValueError):
        return []
    else:
        return messages
