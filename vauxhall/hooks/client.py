"""Telemetry client for sending agent activity to the Vauxhall Dashboard."""

import json
from typing import Any

import paho.mqtt.client as mqtt


def format_message(agent: str, workspace: str, state: str, **details: Any) -> str:
    """Format a telemetry message as a JSON string.

    Args:
        agent: The name of the agent.
        workspace: The workspace directory path.
        state: The current state of the agent.
        **details: Additional key-value pairs for message details.

    Returns:
        str: A JSON-formatted string containing the telemetry data.
    """
    return json.dumps(
        {"agent": agent, "workspace": workspace, "state": state, "details": details}
    )


class TelemetryClient:
    """Client for sending telemetry data via MQTT.

    Connects to an MQTT broker and publishes agent activity messages.
    Failures in connection or publishing are handled silently.
    """

    def __init__(self, host: str = "localhost", port: int = 1883) -> None:
        """Initialize the telemetry client.

        Args:
            host: The MQTT broker hostname. Defaults to "localhost".
            port: The MQTT broker port. Defaults to 1883.
        """
        self.host = host
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def send(self, agent: str, workspace: str, state: str, **details: Any) -> None:
        """Send a telemetry message.

        Formats the message and publishes it to the agent's activity topic.
        Fails silently if an error occurs during connection or publication.

        Args:
            agent: The name of the agent.
            workspace: The workspace directory path.
            state: The current state of the agent.
            **details: Additional key-value pairs for message details.
        """
        payload = format_message(agent, workspace, state, **details)
        topic = f"vauxhall/agents/{agent.lower()}/activity"
        try:
            self.client.connect(self.host, self.port, keepalive=5)
            self.client.publish(topic, payload)
            self.client.disconnect()
        except Exception:
            pass  # Fail silently per spec
