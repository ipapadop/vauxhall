# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Telemetry client for sending agent activity to the Vauxhall Dashboard."""

import json
import time
from collections.abc import Iterable, Mapping
from contextlib import suppress

import paho.mqtt.client as mqtt

from vauxhall.core.config import MQTTConfig
from vauxhall.core.logging import get_logger
from vauxhall.core.mqtt import configure_client
from vauxhall.core.telemetry import SCHEMA_VERSION, telemetry_validation_error
from vauxhall.hooks.config import hook_settings as settings

logger = get_logger(__name__)

# Bounds both the connection attempt and the wait for every acknowledgment,
# so a hook finishes quickly even when the broker is slow or unreachable.
TIMEOUT_SECONDS = 1.0
# paho times the TLS handshake with the keepalive rather than the connection
# timeout, and a hook's connection lasts about a second, so hooks use the
# shortest keepalive instead of mqtt.keepalive.
KEEPALIVE_SECONDS = 1


def format_message(event: Mapping[str, object]) -> str:
    """Encode one telemetry event as its JSON wire payload.

    Args:
        event: The payload fields other than ``schema_version``: ``agent``,
            ``workspace``, ``session_id``, ``state``, and optionally ``env``
            and ``details``.

    Returns:
        The JSON payload, with ``schema_version`` set.

    Raises:
        ValueError: If the event is not valid telemetry.
    """
    payload = {**event, "schema_version": SCHEMA_VERSION}
    error = telemetry_validation_error(payload)
    if error is not None:
        raise ValueError(error)
    # Escaping non-ASCII text takes six bytes per character, or twelve for an
    # emoji, so long details could exceed the dashboard's payload limit. A
    # lone surrogate, which hook input can carry, can't be encoded as UTF-8,
    # so such a payload keeps the escapes.
    text = json.dumps(payload, ensure_ascii=False)
    try:
        text.encode()
    except UnicodeEncodeError:
        return json.dumps(payload)
    return text


def publish(
    events: Iterable[Mapping[str, object]], mqtt_config: MQTTConfig | None = None
) -> bool:
    """Publish telemetry events at QoS 1 over one broker connection.

    Each event goes to its agent's activity topic. Invalid events are logged
    and skipped. Connecting, the TLS handshake, and waiting for all
    acknowledgments each take at most about a second. Failures are logged,
    never raised.

    Args:
        events: Events in the form ``format_message`` takes.
        mqtt_config: Broker settings; defaults to the hooks' settings.

    Returns:
        True when every event was valid and the broker acknowledged it.
    """
    messages: list[tuple[str, str]] = []
    all_valid = True
    for event in events:
        try:
            payload = format_message(event)
        except (TypeError, ValueError):
            logger.debug("Skipping invalid telemetry")
            all_valid = False
            continue
        messages.append((f"vauxhall/agents/{event['agent']}/activity".lower(), payload))
    if not messages:
        return all_valid

    config = mqtt_config or settings.mqtt
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect_timeout = TIMEOUT_SECONDS
    try:
        # A failure stops the connection: it must never fall back to a
        # plaintext or unauthenticated one.
        configure_client(client, config)
    except OSError:
        logger.exception("Could not set up the broker connection")
        return False
    try:
        client.connect(config.host, config.port, keepalive=KEEPALIVE_SECONDS)
    except Exception:
        logger.debug("Failed to connect telemetry client")
        return False

    try:
        client.loop_start()
        results = [client.publish(topic, payload, qos=1) for topic, payload in messages]
        deadline = time.monotonic() + TIMEOUT_SECONDS
        for result in results:
            result.wait_for_publish(max(0.0, deadline - time.monotonic()))
        delivered = all(result.is_published() for result in results)
        if delivered:
            logger.debug("Successfully sent telemetry (%d events)", len(messages))
        else:
            logger.debug("Timed out sending telemetry")
    except Exception:
        logger.debug("Failed to send telemetry")
        delivered = False
    finally:
        with suppress(Exception):
            client.disconnect()
        with suppress(Exception):
            client.loop_stop()
    return delivered and all_valid
