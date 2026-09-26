# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""MQTT client for the Vauxhall Dashboard."""

import json
import uuid
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from vauxhall.core.logging import get_logger
from vauxhall.core.prompts import (
    ACK_KIND,
    ACK_TOPIC_FILTER,
    PROMPT_KIND,
    format_prompt,
    parse_ack,
    parse_session_topic,
    session_topic,
)
from vauxhall.core.telemetry import validate_telemetry
from vauxhall.dashboard.config import dashboard_settings as settings

logger = get_logger(__name__)


class DashboardSubscriber:
    """Subscribes to agent telemetry topics and forwards data to a callback.

    It also publishes prompts for agent sessions and forwards their
    acknowledgments.
    """

    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None],
        status_callback: Callable[[str], None],
        host: str | None = None,
        port: int | None = None,
        ack_callback: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        """Initialize the subscriber.

        Args:
            callback: Function to call when telemetry data is received.
            status_callback: Function to call with connection status updates.
            host: MQTT broker host. Defaults to settings.mqtt.host.
            port: MQTT broker port. Defaults to settings.mqtt.port.
            ack_callback: Function to call with each prompt acknowledgment, a
                dict with ``id``, ``status``, and optionally ``reason``.
        """
        self.callback = callback
        self.status_callback = status_callback
        self.ack_callback = ack_callback
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
        """Internal callback for MQTT connection.

        Args:
            client: The connected client, used to subscribe on success.
            userdata: Unused paho user data.
            flags: Connection flags reported by the broker.
            reason_code: The broker's result code; zero means connected.
            properties: MQTT v5 properties, if any.
        """
        if self._stopping:
            return
        if reason_code == 0:
            self._ever_connected = True
            logger.info("Connected to MQTT broker at %s:%d", self.host, self.port)
            self.status_callback("Connected to Agent Fleet")
            client.subscribe("vauxhall/agents/+/activity")
            client.subscribe("vauxhall/agents/+/status")
            client.subscribe(ACK_TOPIC_FILTER, qos=1)
            logger.info("Subscribed to agent telemetry topics.")
        else:
            logger.error("Failed to connect to MQTT broker: %s", reason_code)
            self.status_callback(f"Connection failed: {reason_code}. Retrying...")

    def _on_connect_fail(self, client: mqtt.Client, userdata: object) -> None:
        """Report asynchronous connection failures while retrying.

        Args:
            client: The client that failed to connect.
            userdata: Unused paho user data.
        """
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
        """Internal callback for MQTT disconnection.

        Args:
            client: The disconnected client.
            userdata: Unused paho user data.
            disconnect_flags: Disconnection flags reported by paho.
            reason_code: The reason the connection ended.
            properties: MQTT v5 properties, if any.
        """
        if self._stopping:
            return
        logger.warning("Disconnected from MQTT broker; retrying")
        self.status_callback("Disconnected. Retrying...")

    def _on_message(
        self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage
    ) -> None:
        """Validate one MQTT telemetry message and forward it to the callback.

        Args:
            client: The client that received the message.
            userdata: Unused paho user data.
            msg: The received message, dropped when oversized or invalid.
        """
        payload = msg.payload
        if len(payload) > settings.dashboard.max_payload_bytes:
            logger.warning(
                "Dropping oversized MQTT message on topic %s (%d bytes)",
                msg.topic,
                len(payload),
            )
            return

        session_topic_parts = parse_session_topic(msg.topic)
        if session_topic_parts is not None:
            if session_topic_parts[2] == ACK_KIND:
                self._on_ack(payload)
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

    def _on_ack(self, payload: bytes) -> None:
        """Validate a prompt acknowledgment and forward it to the callback.

        Args:
            payload: The raw acknowledgment, dropped when invalid.
        """
        ack = parse_ack(payload)
        if ack is None:
            logger.warning("Dropping invalid prompt acknowledgment")
        elif self.ack_callback is not None:
            self.ack_callback(ack)

    def send_prompt(self, agent: str, session_id: str, text: str) -> str:
        """Publish a prompt to one agent session at QoS 1, never retained.

        A retained prompt would be typed again each time a relay reconnects.

        Args:
            agent: The agent name of the session's card.
            session_id: The session identity of the card.
            text: The prompt to send.

        Returns:
            The identifier its acknowledgment will carry.

        Raises:
            ValueError: If the text is not an acceptable prompt.
            ConnectionError: If the broker did not accept the message.
        """
        message_id = uuid.uuid4().hex
        payload = format_prompt(message_id, text)
        if not self.client.is_connected():
            message = "Not connected to the broker"
            raise ConnectionError(message)
        result = self.client.publish(
            session_topic(agent, session_id, PROMPT_KIND), payload, qos=1, retain=False
        )
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            message = "The broker did not accept the prompt"
            raise ConnectionError(message)
        return message_id

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
