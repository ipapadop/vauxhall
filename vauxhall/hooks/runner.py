# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Run one hook process: read the event, publish its telemetry, answer the agent."""

import json
import sys
from collections.abc import Callable, Mapping
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from vauxhall.core.config import ConfigurationError
from vauxhall.core.logging import get_logger
from vauxhall.hooks.events import EventHandler, Telemetry
from vauxhall.hooks.identity import publishable_workspace, resolve_session_id
from vauxhall.hooks.text import truncate_text

logger = get_logger(__name__)


def event_workspace(
    input_data: dict[str, Any], current_directory: Callable[[], Path] = Path.cwd
) -> str | None:
    """Return the workspace of a hook event.

    Args:
        input_data: The hook event.
        current_directory: Returns the process directory, used when the event
            has no non-blank ``cwd`` string.

    Returns:
        The workspace, or None when the process directory is gone too.
    """
    workspace = input_data.get("cwd")
    if isinstance(workspace, str) and workspace.strip():
        return workspace
    try:
        return str(current_directory())
    except OSError:
        return None


def publish_telemetry(
    input_data: dict[str, Any],
    agent: str,
    handlers: Mapping[str, EventHandler],
    publish: Callable[[list[dict[str, Any]]], bool] | None = None,
    messages: list[str] | None = None,
) -> None:
    """Translate one hook event with its handler and publish the telemetry.

    Events without a handler, or whose handler returns None, publish nothing.

    Args:
        input_data: The hook event to translate.
        agent: The agent name published with the telemetry.
        handlers: Event handler, keyed by hook event name.
        publish: Publishes the events, defaulting to
            ``vauxhall.hooks.client.publish``.
        messages: Interim assistant messages to publish before the event.
    """
    hook_type = input_data.get("hook_event_name")
    handler = handlers.get(hook_type) if isinstance(hook_type, str) else None
    telemetry = handler(input_data) if handler is not None else None
    if telemetry is None and not messages:
        return

    session_id = resolve_session_id(input_data)
    if session_id is None:
        logger.warning("Skipping telemetry: no stable session identity is available")
        return
    workspace = event_workspace(input_data)
    if workspace is None:
        logger.warning("Skipping telemetry: no workspace is available")
        return

    events: list[Telemetry] = [
        ("Thinking", {"message": message}) for message in messages or []
    ]
    if telemetry is not None:
        events.append(telemetry)
    if publish is None:
        from vauxhall.hooks.client import publish  # noqa: PLC0415

    workspace = publishable_workspace(workspace)
    publish(
        [
            {
                "agent": agent,
                "workspace": workspace,
                "session_id": session_id,
                "state": state,
                # A value over the schema's limit would drop the whole event.
                "details": {
                    key: truncate_text(value) if isinstance(value, str) else value
                    for key, value in details.items()
                },
            }
            for state, details in events
        ]
    )


def run_hook(send_telemetry: Callable[[dict[str, Any]], None]) -> None:
    """Process one hook event from stdin without disrupting the hook protocol.

    Errors never reach stdout, which always receives the empty JSON object the
    hook protocol expects.

    Args:
        send_telemetry: Callable that publishes telemetry for one hook event.
    """
    try:
        with redirect_stdout(sys.stderr):
            from vauxhall.core.logging import setup_logging  # noqa: PLC0415
            from vauxhall.hooks.config import (  # noqa: PLC0415
                hook_settings,
                warn_about_workspace_file,
            )

            setup_logging(level=hook_settings.logging.level)
            warn_about_workspace_file()
            input_data = json.load(sys.stdin)
            if isinstance(input_data, dict):
                send_telemetry(input_data)
    except ConfigurationError as error:
        print(error, file=sys.stderr)
    except Exception:
        pass
    print("{}")
