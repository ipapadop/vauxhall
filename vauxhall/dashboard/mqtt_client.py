"""MQTT client for the Vauxhall Dashboard."""

import json
from typing import Any, Callable

import paho.mqtt.client as mqtt


class DashboardSubscriber:
    """Subscribes to agent telemetry topics and forwards data to a callback."""

    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None],
        host: str = "localhost",
        port: int = 1883,
    ) -> None:
        """Initialize the subscriber.

        Args:
            callback: Function to call when telemetry data is received.
            host: MQTT broker host. Defaults to "localhost".
            port: MQTT broker port. Defaults to 1883.
        """
        self.callback = callback
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self._on_message
        self.host = host
        self.port = port

    def _on_message(
        self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage
    ) -> None:
        """Internal callback for MQTT messages.

        Args:
            client: The MQTT client instance.
            userdata: Private user data.
            msg: The received message.
        """
        try:
            data = json.loads(msg.payload.decode())
            self.callback(data)
        except Exception:
            pass

    def start(self) -> None:
        """Connect to the broker and start the background loop."""
        self.client.connect(self.host, self.port)
        self.client.subscribe("vauxhall/agents/+/activity")
        self.client.subscribe("vauxhall/agents/+/status")
        self.client.loop_start()

    def stop(self) -> None:
        """Stop the background loop and disconnect from the broker."""
        self.client.loop_stop()
        self.client.disconnect()
