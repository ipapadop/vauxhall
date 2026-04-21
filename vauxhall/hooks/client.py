# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Telemetry client for sending agent activity to the Vauxhall Dashboard."""

import json

import paho.mqtt.client as mqtt

from vauxhall.config import settings
from vauxhall.logging_config import get_logger

logger = get_logger(__name__)


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

    def send(
        self,
        agent: str,
        workspace: str,
        state: str,
        env: str | None = None,
        **details: object,
    ) -> None:
        """Send a telemetry message.

        Formats the message and publishes it to the agent's activity topic.
        Fails silently if an error occurs during connection or publication.

        Args:
            agent: The name of the agent.
            workspace: The workspace directory path.
            state: The current state of the agent.
            env: Optional execution environment (local, remote).
            **details: Additional key-value pairs for message details.
        """
        payload = format_message(agent, workspace, state, env, **details)
        topic = f"vauxhall/agents/{agent.lower()}/activity"
        try:
            self.client.connect(self.host, self.port, keepalive=settings.mqtt.keepalive)
            publish_result = self.client.publish(topic, payload)
            publish_result.wait_for_publish()
            self.client.disconnect()
            logger.debug("Successfully sent telemetry for %s to %s", agent, topic)
        except Exception:
            logger.debug("Failed to send telemetry for %s", agent)
            # Fail silently per spec
