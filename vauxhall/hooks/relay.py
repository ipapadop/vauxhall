# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Relay that types dashboard prompts into the tmux panes of local agent sessions.

Hooks are short-lived, so nothing on the agent side can receive a prompt. This
long-lived process subscribes to the per-session prompt topics, looks up the
tmux pane a hook recorded for the session, pastes the prompt into it, and
publishes an acknowledgment. A prompt for a session this machine doesn't know
is ignored, so one relay per agent machine can share a broker.
"""

import hashlib
import subprocess
import time
from collections import OrderedDict
from collections.abc import Callable

import paho.mqtt.client as mqtt

from vauxhall.core.config import ConfigurationError
from vauxhall.core.logging import get_logger, setup_logging
from vauxhall.core.prompts import (
    ACK_KIND,
    PROMPT_KIND,
    PROMPT_TOPIC_FILTER,
    format_ack,
    parse_prompt,
    parse_session_topic,
    session_topic,
)
from vauxhall.hooks.panes import PaneTarget, load_pane

logger = get_logger(__name__)

TMUX_TIMEOUT_SECONDS = 5.0
# The agent's terminal input needs a moment to take the paste before Enter.
SUBMIT_DELAY_SECONDS = 0.2
_SEEN_LIMIT = 256

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


def _tmux(
    target: PaneTarget, *arguments: str, data: bytes | None = None, run: Runner
) -> "subprocess.CompletedProcess[bytes]":
    """Run one tmux command against the server a pane belongs to.

    Args:
        target: The pane whose tmux server is addressed.
        *arguments: The tmux command and its arguments.
        data: Text for the command's standard input.
        run: Function that runs the command, ``subprocess.run`` by default.

    Returns:
        The completed process.
    """
    command = ["tmux"]
    if target.socket:
        command += ["-S", target.socket]
    return run(
        [*command, *arguments],
        input=data,
        capture_output=True,
        timeout=TMUX_TIMEOUT_SECONDS,
        check=True,
    )


def deliver_prompt(
    target: PaneTarget,
    message_id: str,
    text: str,
    run: Runner = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """Paste a prompt into a pane and submit it.

    The text goes in through a private tmux buffer as a bracketed paste, which
    keeps newlines and shell or key-name syntax in the text from being
    interpreted the way ``send-keys`` would.

    Args:
        target: The pane to type into.
        message_id: Identifier used to name the temporary tmux buffer.
        text: The validated prompt.
        run: Function that runs tmux, ``subprocess.run`` by default.
        sleep: Function that waits, ``time.sleep`` by default.

    Returns:
        ``None`` on success, otherwise the failure reason to acknowledge.
    """
    try:
        # The pane id alone can name an unrelated pane after tmux restarts.
        server = _tmux(
            target, "display-message", "-p", "-t", target.pane, "#{pid}", run=run
        )
    except (OSError, subprocess.SubprocessError):
        return "pane-unavailable"
    if (
        target.server_pid is not None
        and server.stdout.strip() != str(target.server_pid).encode()
    ):
        return "pane-unavailable"

    buffer = "vauxhall-" + hashlib.sha256(message_id.encode()).hexdigest()[:16]
    try:
        _tmux(target, "load-buffer", "-b", buffer, "-", data=text.encode(), run=run)
        _tmux(
            target, "paste-buffer", "-d", "-p", "-b", buffer, "-t", target.pane, run=run
        )
        sleep(SUBMIT_DELAY_SECONDS)
        _tmux(target, "send-keys", "-t", target.pane, "Enter", run=run)
    except (OSError, subprocess.SubprocessError):
        try:
            _tmux(target, "delete-buffer", "-b", buffer, run=run)
        except (OSError, subprocess.SubprocessError):
            logger.debug("Could not remove the tmux buffer after a failed delivery")
        return "delivery-failed"
    return None


class PromptRelay:
    """Delivers prompts received over MQTT and acknowledges each one."""

    def __init__(
        self,
        host: str,
        port: int,
        keepalive: int,
        deliver: Callable[[PaneTarget, str, str], str | None] = deliver_prompt,
    ) -> None:
        """Initialize the relay.

        Args:
            host: The MQTT broker host.
            port: The MQTT broker port.
            keepalive: The MQTT keepalive in seconds.
            deliver: Function that pastes a prompt into a pane, given the pane,
                the message identifier, and the text.
        """
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.deliver = deliver
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._seen: OrderedDict[tuple[str, str, str], None] = OrderedDict()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Subscribe to prompts each time the broker connection is established.

        Args:
            client: The connected client.
            userdata: Unused paho user data.
            flags: Connection flags reported by the broker.
            reason_code: The broker's result code; zero means connected.
            properties: MQTT v5 properties, if any.
        """
        if reason_code == 0:
            client.subscribe(PROMPT_TOPIC_FILTER, qos=1)
            logger.info("Relay connected to %s:%d", self.host, self.port)
        else:
            logger.error("Relay could not connect to the broker: %s", reason_code)

    def _is_duplicate(self, identity: tuple[str, str, str]) -> bool:
        """Remember a prompt and report whether it was already handled.

        QoS 1 can deliver a message twice, and typing a prompt twice would
        submit it twice.

        Args:
            identity: The agent, session, and message identifier.

        Returns:
            Whether the prompt was seen before.
        """
        if identity in self._seen:
            return True
        self._seen[identity] = None
        while len(self._seen) > _SEEN_LIMIT:
            self._seen.popitem(last=False)
        return False

    def _on_message(
        self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage
    ) -> None:
        """Deliver one prompt to its session's pane and acknowledge the result.

        Args:
            client: The client that received the message.
            userdata: Unused paho user data.
            msg: The received message; dropped when invalid or for a session
                that isn't running in tmux on this machine.
        """
        parsed_topic = parse_session_topic(msg.topic)
        if parsed_topic is None or parsed_topic[2] != PROMPT_KIND:
            return
        agent, session_id, _ = parsed_topic
        prompt = parse_prompt(msg.payload)
        if prompt is None:
            logger.warning("Dropping invalid prompt message for %s", agent)
            return
        message_id, text = prompt

        target = load_pane(agent, session_id)
        if target is None:
            logger.debug("Ignoring a prompt for a session not started here: %s", agent)
            return
        if self._is_duplicate((agent, session_id, message_id)):
            logger.debug("Ignoring a repeated prompt for %s", agent)
            return

        reason = self.deliver(target, message_id, text)
        if reason is None:
            logger.info("Delivered a prompt to %s in pane %s", agent, target.pane)
            payload = format_ack(message_id, "delivered")
        else:
            logger.warning("Could not deliver a prompt to %s: %s", agent, reason)
            payload = format_ack(message_id, "failed", reason)
        # The network loop is running this callback, so waiting for the
        # broker here would never finish.
        client.publish(session_topic(agent, session_id, ACK_KIND), payload, qos=1)

    def run(self) -> None:
        """Connect and relay prompts until interrupted."""
        self.client.connect_async(self.host, self.port, keepalive=self.keepalive)
        try:
            self.client.loop_forever(retry_first_connection=True)
        except KeyboardInterrupt:
            logger.info("Relay stopping")
        finally:
            self.client.disconnect()


def main() -> None:
    """Run the prompt relay with the hooks' broker settings."""
    try:
        from vauxhall.hooks.config import hook_settings  # noqa: PLC0415
    except ConfigurationError as error:
        raise SystemExit(str(error)) from error

    setup_logging(level=hook_settings.logging.level)
    relay = PromptRelay(
        hook_settings.mqtt.host, hook_settings.mqtt.port, hook_settings.mqtt.keepalive
    )
    relay.run()


if __name__ == "__main__":
    main()
