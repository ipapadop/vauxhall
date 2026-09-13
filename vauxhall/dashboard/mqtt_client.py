# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""MQTT client for the Vauxhall Dashboard."""

import json
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from vauxhall.core.logging import get_logger
from vauxhall.core.telemetry import validate_telemetry
from vauxhall.dashboard.config import dashboard_settings as settings

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
        self.client.on_connect_fail = self._on_connect_fail
        self.client.on_disconnect = self._on_disconnect
        self.host = host if host is not None else settings.mqtt.host
        self.port = port if port is not None else settings.mqtt.port
        self._stopping = False
        self._loop_started = False
        self._ever_connected = False

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Internal callback for MQTT connection."""
        if self._stopping:
            return
        if reason_code == 0:
            self._ever_connected = True
            logger.info("Connected to MQTT broker at %s:%d", self.host, self.port)
            self.status_callback("Connected to Agent Fleet")
            client.subscribe("vauxhall/agents/+/activity")
            client.subscribe("vauxhall/agents/+/status")
            logger.info("Subscribed to agent telemetry topics.")
        else:
            logger.error("Failed to connect to MQTT broker: %s", reason_code)
            self.status_callback(f"Connection failed: {reason_code}. Retrying...")

    def _on_connect_fail(self, client: mqtt.Client, userdata: object) -> None:
        """Report asynchronous connection failures while retrying."""
        if not self._stopping:
            self.status_callback("Connection failed. Retrying...")

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Internal callback for MQTT disconnection."""
        if self._stopping:
            return
        logger.warning("Disconnected from MQTT broker; retrying")
        self.status_callback("Disconnected. Retrying...")

    def _on_message(
        self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage
    ) -> None:
        """Internal callback for MQTT messages.

        Args:
            client: The MQTT client instance.
            userdata: Private user data.
            msg: The received message.
        """
        payload = msg.payload
        if len(payload) > settings.dashboard.max_payload_bytes:
            logger.warning(
                "Dropping oversized MQTT message on topic %s (%d bytes)",
                msg.topic,
                len(payload),
            )
            return

        try:
            data = json.loads(payload.decode())
        except Exception:
            logger.warning("Dropping malformed MQTT message on topic %s", msg.topic)
            return

        telemetry = validate_telemetry(data)
        if telemetry is None:
            logger.warning("Dropping invalid telemetry message on topic %s", msg.topic)
            return

        logger.debug("Received MQTT message on topic: %s", msg.topic)
        self.callback(telemetry)

    def start(self) -> None:
        """Connect to the broker and start the background loop."""
        logger.info("Connecting to MQTT broker at %s:%d...", self.host, self.port)
        self._stopping = False
        self.status_callback("Connecting...")
        try:
            self.client.connect_async(
                self.host, self.port, keepalive=settings.mqtt.keepalive
            )
            self.client.loop_start()
            self._loop_started = True
        except Exception:
            logger.warning("Failed to initialize async connection to MQTT broker")
            self.status_callback("Connection failed")
            if self._loop_started:
                self.client.loop_stop()
                self._loop_started = False
            raise

    def stop(self) -> None:
        """Stop the background loop and disconnect from the broker."""
        if self._stopping:
            return
        self._stopping = True
        if not self._loop_started:
            return
        logger.info("Disconnecting from MQTT broker...")
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
            self._loop_started = False
            self.status_callback("Disconnected")
