# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Telemetry client for sending agent activity to the Vauxhall Dashboard."""

import json
from typing import Self

import paho.mqtt.client as mqtt

from vauxhall.core.logging import get_logger
from vauxhall.hooks.config import hook_settings as settings

logger = get_logger(__name__)

PUBLISH_TIMEOUT_SECONDS = 1.0


def format_message(
    agent: str, workspace: str, state: str, env: str | None = None, **details: object
) -> str:
    """Format a telemetry message as a JSON string.

    Args:
        agent: The name of the agent.
        workspace: The workspace directory path.
        state: The current state of the agent.
        env: Optional execution environment (local, remote).
        **details: Additional key-value pairs for message details.

    Returns:
        str: A JSON-formatted string containing the telemetry data.
    """
    payload_dict = {
        "agent": agent,
        "workspace": workspace,
        "state": state,
        "details": details,
    }
    if env:
        payload_dict["env"] = env

    return json.dumps(payload_dict)


class TelemetryClient:
    """Client for sending telemetry data via MQTT.

    Connects to an MQTT broker and publishes agent activity messages.
    Failures in connection or publishing are handled silently.
    """

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        """Initialize the telemetry client.

        Args:
            host: The MQTT broker hostname. Defaults to settings.mqtt.host.
            port: The MQTT broker port. Defaults to settings.mqtt.port.
        """
        self.host = host if host is not None else settings.mqtt.host
        self.port = port if port is not None else settings.mqtt.port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.is_connected = False
        self._managed = False
        self._loop_running = False

    def __enter__(self) -> Self:
        """Enter the context manager, establishing a persistent connection."""
        self._managed = True
        try:
            self.client.connect(self.host, self.port, keepalive=settings.mqtt.keepalive)
            self.is_connected = True
            self.client.loop_start()
            self._loop_running = True
        except Exception:
            logger.debug("Failed to connect telemetry client inside context manager")
            self._close_connection()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Exit the context manager, closing the connection."""
        self._close_connection()
        self._managed = False

    def _close_connection(self) -> None:
        """Close MQTT transport without allowing cleanup failures to escape."""
        if self.is_connected:
            try:
                self.client.disconnect()
            except Exception:
                logger.debug("Failed to disconnect telemetry client")
            finally:
                self.is_connected = False

        if self._loop_running:
            try:
                self.client.loop_stop()
            except Exception:
                logger.debug("Failed to stop telemetry client network loop")
            finally:
                self._loop_running = False

    def send(
        self,
        agent: str,
        workspace: str,
        state: str,
        env: str | None = None,
        **details: object,
    ) -> bool:
        """Send a telemetry message.

        Formats the message and publishes it to the agent's activity topic.
        Fails silently if an error occurs during connection or publication.

        Args:
            agent: The name of the agent.
            workspace: The workspace directory path.
            state: The current state of the agent.
            env: Optional execution environment (local, remote).
            **details: Additional key-value pairs for message details.

        Returns:
            True when the broker acknowledges publication; otherwise False.
        """
        one_shot = not self._managed
        try:
            payload = format_message(agent, workspace, state, env, **details)
            topic = f"vauxhall/agents/{agent.lower()}/activity"

            if self._managed and not self.is_connected:
                return False

            if not self.is_connected:
                self.client.connect(
                    self.host, self.port, keepalive=settings.mqtt.keepalive
                )
                self.is_connected = True
                self.client.loop_start()
                self._loop_running = True

            publish_result = self.client.publish(topic, payload, qos=1)
            publish_result.wait_for_publish(PUBLISH_TIMEOUT_SECONDS)
            delivered = publish_result.is_published()
        except Exception:
            logger.debug("Failed to send telemetry for %s", agent)
            return False
        else:
            if delivered:
                logger.debug("Successfully sent telemetry for %s to %s", agent, topic)
            else:
                logger.debug("Timed out sending telemetry for %s", agent)
            return delivered
        finally:
            if one_shot:
                self._close_connection()
