# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""MQTT client for the Vauxhall Dashboard."""

import json
from collections.abc import Callable
from queue import SimpleQueue
from threading import Thread
from typing import Any

import paho.mqtt.client as mqtt

from vauxhall.core.logging import get_logger
from vauxhall.core.mqtt import configure_client
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
        """Connect to the broker and start the background loop.

        A failure to set up credentials or TLS is reported through the status
        callback and leaves the subscriber stopped.
        """
        if self._stopping:
            message = "A closed subscriber can't be started again"
            raise RuntimeError(message)
        logger.info("Connecting to MQTT broker at %s:%d...", self.host, self.port)
        self.status_callback("Connecting...")
        try:
            configure_client(self.client, settings.mqtt)
        except OSError as error:
            logger.exception("Could not set up the broker connection")
            self.status_callback(f"Connection failed: {error}")
            return
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

    def close(self, closer: "SubscriberCloser") -> None:
        """Silence status callbacks and disconnect, leaving the wait to ``closer``.

        The caller is the UI thread, and ``loop_stop()`` joins a network
        thread that can be inside a connect attempt for up to paho's 5-second
        connect timeout. No status is reported: a replacement reports its own,
        and at shutdown the window is gone. Messages that arrive before the
        disconnect are still forwarded: they describe agents. A closed
        subscriber can't be started again.

        Args:
            closer: Stops the network loop on its own thread.
        """
        if self._stopping:
            return
        self._stopping = True
        if not self._loop_started:
            return
        logger.info("Disconnecting from MQTT broker at %s:%d", self.host, self.port)
        try:
            self.client.disconnect()
        except Exception:
            logger.exception("Could not disconnect from the MQTT broker")
        closer.add(self)

    def stop_loop(self) -> None:
        """Wait for the network loop to end, logging rather than raising errors."""
        try:
            self.client.loop_stop()
        except Exception:
            logger.exception("Could not stop the MQTT network loop")


class SubscriberCloser:
    """Stops closed subscribers' network loops, one at a time, on one thread.

    A single thread serves every broker change, so repeated changes to an
    unreachable broker don't each start a thread that waits on a connect.
    """

    def __init__(self) -> None:
        """Initialize the closer; its thread starts with the first subscriber."""
        self._queue: SimpleQueue[DashboardSubscriber | None] = SimpleQueue()
        self._thread: Thread | None = None

    def add(self, subscriber: DashboardSubscriber) -> None:
        """Queue a closed subscriber whose network loop must be stopped.

        Args:
            subscriber: The subscriber, already disconnected.
        """
        if self._thread is None:
            self._thread = Thread(
                target=self._run, name="vauxhall-mqtt-closer", daemon=True
            )
            self._thread.start()
        self._queue.put(subscriber)

    def finish(self, timeout: float) -> bool:
        """Wait for every queued network loop to stop, up to a time limit.

        Args:
            timeout: Seconds to wait.

        Returns:
            bool: Whether they all stopped. A loop still inside a connect
                attempt runs on a daemon thread that ends with the process.
        """
        if self._thread is None:
            return True
        self._queue.put(None)
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        """Stop each queued subscriber's network loop until told to finish."""
        while (subscriber := self._queue.get()) is not None:
            subscriber.stop_loop()
