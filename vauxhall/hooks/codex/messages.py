# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Best-effort interim Codex messages from the local session record."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from vauxhall.core.files import NOFOLLOW, write_atomically
from vauxhall.core.logging import get_logger
from vauxhall.core.telemetry import message_text
from vauxhall.hooks.scratch import claim, private_directory, remove_old_files

logger = get_logger(__name__)

_MAX_READ_BYTES = 1_048_576
# Claimed cursors and temporary files are left only by a hook that died.
_LEFTOVER_MAX_AGE_SECONDS = 86400


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


def _read_from_cursor(
    cursor: Path, transcript: Path, size: int, turn_id: str
) -> tuple[list[str], int]:
    """Read the commentary completed past a cursor.

    Args:
        cursor: The file holding the offset read so far.
        transcript: The session record.
        size: The session record's size.
        turn_id: The turn whose commentary is wanted.

    Returns:
        The commentary, oldest first, and the offset of the first record not
        read.

    Raises:
        OSError: If the session record cannot be read.
    """
    try:
        saved = os.open(cursor, os.O_RDONLY | NOFOLLOW)
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
    return messages, next_offset


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
    if not (
        isinstance(transcript_path, str)
        and transcript_path
        and isinstance(session_id, str)
        and session_id
        and isinstance(turn_id, str)
        and turn_id
    ):
        return []
    try:
        transcript = Path(transcript_path)
        cursor = _cursor_path(session_id, transcript_path)
        if input_data.get("hook_event_name") == "UserPromptSubmit":
            write_atomically(
                cursor,
                str(transcript.stat().st_size),
                private=True,
                durable=False,
            )
            # Cursors are named by a bare hash; only leftovers have a suffix.
            remove_old_files(cursor.parent, "*.*", _LEFTOVER_MAX_AGE_SECONDS)
            return []
        if input_data.get("hook_event_name") not in {
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "Stop",
        }:
            return []
        # Hooks run as separate processes. Renaming the cursor claims it, so a
        # concurrent event neither reports the same records nor moves the
        # cursor back. While it is claimed, or before UserPromptSubmit writes
        # it, the rename fails and the event reports nothing; a later event in
        # the turn catches up.
        claimed = claim(cursor)
        try:
            # Sized after claiming: an event that claimed it first may have
            # read past an earlier size, which would look like a new record.
            size = transcript.stat().st_size
            messages, next_offset = _read_from_cursor(
                claimed, transcript, size, turn_id
            )
            write_atomically(cursor, str(next_offset), private=True, durable=False)
        except BaseException:
            claimed.replace(cursor)
            raise
        try:
            claimed.unlink()
        except OSError as error:
            logger.warning("Could not remove a claimed Codex cursor: %s", error)
    except (OSError, ValueError):
        return []
    else:
        return messages
