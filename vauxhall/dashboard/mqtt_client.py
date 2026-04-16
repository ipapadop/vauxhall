# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""MQTT client for the Vauxhall Dashboard."""

import json
from typing import Any, Callable

import paho.mqtt.client as mqtt

from vauxhall.config import settings
from vauxhall.logging_config import get_logger

logger = get_logger(__name__)


class DashboardSubscriber:
    """Subscribes to agent telemetry topics and forwards data to a callback."""

    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None],
        status_callback: Callable[[str], None],
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Initialize the subscriber.

        Args:
            callback: Function to call when telemetry data is received.
            status_callback: Function to call with connection status updates.
            host: MQTT broker host. Defaults to settings.mqtt.host.
            port: MQTT broker port. Defaults to settings.mqtt.port.
        """
        self.callback = callback
        self.status_callback = status_callback
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.host = host if host is not None else settings.mqtt.host
        self.port = port if port is not None else settings.mqtt.port

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        """Internal callback for MQTT connection."""
        if reason_code == 0:
            logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
            self.status_callback("Connected to Agent Fleet")
            client.subscribe("vauxhall/agents/+/activity")
            client.subscribe("vauxhall/agents/+/status")
            logger.info("Subscribed to agent telemetry topics.")
        else:
            logger.error(f"Failed to connect to MQTT broker: {reason_code}")
            self.status_callback(f"Connection Failed: {reason_code}")

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        """Internal callback for MQTT disconnection."""
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
        self.status_callback("Disconnected. Retrying...")

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
            logger.debug(f"Received MQTT message on topic: {msg.topic}")
            self.callback(data)
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def start(self) -> None:
        """Connect to the broker and start the background loop."""
        logger.info(f"Connecting to MQTT broker at {self.host}:{self.port}...")
        try:
            self.client.connect(self.host, self.port, keepalive=settings.mqtt.keepalive)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Could not connect to MQTT broker: {e}")

    def stop(self) -> None:
        """Stop the background loop and disconnect from the broker."""
        logger.info("Disconnecting from MQTT broker...")
        self.client.loop_stop()
        self.client.disconnect()
