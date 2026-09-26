# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the tmux prompt relay."""

import subprocess
from dataclasses import dataclass, field

import pytest

from vauxhall.core.prompts import (
    ACK_KIND,
    PROMPT_KIND,
    format_prompt,
    parse_ack,
    session_topic,
)
from vauxhall.hooks import panes, relay
from vauxhall.hooks.panes import PaneTarget

TARGET = PaneTarget("%3", "/run/tmux-1000/default", 4242)
TEXT = "line one\nline two; rm -rf ~ #{pid} `x`"


def command_name(command: list[str]) -> str:
    """Return the tmux subcommand of a command line.

    Args:
        command: The command line, with or without ``-S <socket>``.

    Returns:
        The subcommand name.
    """
    return command[3] if command[1] == "-S" else command[1]


class FakeTmux:
    """Records tmux commands and answers like a healthy server."""

    def __init__(
        self, server_pid: str = "4242", fail_on: frozenset[str] = frozenset()
    ) -> None:
        """Create the fake.

        Args:
            server_pid: What ``display-message`` reports as the server PID.
            fail_on: The tmux subcommands that fail.
        """
        self.commands: list[list[str]] = []
        self.inputs: list[bytes | None] = []
        self.server_pid = server_pid
        self.fail_on = fail_on

    def __call__(
        self, command: list[str], **options: object
    ) -> "subprocess.CompletedProcess[bytes]":
        """Run a fake tmux command.

        Args:
            command: The command line.
            **options: The ``subprocess.run`` options, of which only ``input``
                is recorded.

        Returns:
            A completed process.

        Raises:
            subprocess.CalledProcessError: For a subcommand set to fail.
        """
        assert options["check"] is True
        assert options["timeout"] == relay.TMUX_TIMEOUT_SECONDS
        self.commands.append(command)
        self.inputs.append(options.get("input"))  # type: ignore[arg-type]
        name = command_name(command)
        if name in self.fail_on:
            raise subprocess.CalledProcessError(1, command)
        stdout = f"{self.server_pid}\n".encode() if name == "display-message" else b""
        return subprocess.CompletedProcess(command, 0, stdout, b"")


def names(tmux: FakeTmux) -> list[str]:
    """Return the subcommands a fake tmux ran, in order.

    Args:
        tmux: The fake.

    Returns:
        The subcommand names.
    """
    return [command_name(command) for command in tmux.commands]


def test_deliver_pastes_the_text_and_submits() -> None:
    """The prompt is pasted as a bracketed paste, then Enter is sent."""
    tmux = FakeTmux()
    sleeps: list[float] = []

    result = relay.deliver_prompt(TARGET, "id-1", TEXT, tmux, sleeps.append)

    assert result is None
    assert names(tmux) == [
        "display-message",
        "load-buffer",
        "paste-buffer",
        "send-keys",
    ]
    assert all(
        command[:3] == ["tmux", "-S", TARGET.socket] for command in tmux.commands
    )
    _, load, paste, keys = tmux.commands
    assert tmux.inputs[1] == TEXT.encode()
    assert "-p" in paste
    assert paste[paste.index("-t") + 1] == "%3"
    assert paste[paste.index("-b") + 1] == load[load.index("-b") + 1]
    assert keys[-3:] == ["-t", "%3", "Enter"]
    assert sleeps == [relay.SUBMIT_DELAY_SECONDS]
    # The text reaches tmux only through standard input, never a command line.
    assert not any("rm -rf" in " ".join(command) for command in tmux.commands)


def test_deliver_uses_the_default_socket_when_none_was_recorded() -> None:
    """Without a recorded socket tmux is not given ``-S``."""
    tmux = FakeTmux()

    relay.deliver_prompt(
        PaneTarget("%3", None, None), "id-1", "hi", tmux, lambda _: None
    )

    assert all(
        command[0] == "tmux" and "-S" not in command for command in tmux.commands
    )


def test_deliver_refuses_a_pane_of_a_restarted_server() -> None:
    """After a tmux restart the recorded pane id may name an unrelated pane."""
    tmux = FakeTmux(server_pid="9999")

    result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result == "pane-unavailable"
    assert names(tmux) == ["display-message"]


def test_deliver_reports_a_missing_pane() -> None:
    """A pane tmux no longer knows is unavailable."""
    tmux = FakeTmux(fail_on=frozenset({"display-message"}))

    assert relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None) == (
        "pane-unavailable"
    )


@pytest.mark.parametrize("failing", ["paste-buffer", "send-keys"])
def test_deliver_cleans_up_after_a_failure(failing: str) -> None:
    """A failed step reports failure and removes the temporary buffer.

    Args:
        failing: The tmux subcommand that fails.
    """
    tmux = FakeTmux(fail_on=frozenset({failing}))

    result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result == "delivery-failed"
    assert names(tmux)[-1] == "delete-buffer"


def test_deliver_survives_a_failed_cleanup() -> None:
    """A buffer that cannot be removed doesn't hide the delivery failure."""
    tmux = FakeTmux(fail_on=frozenset({"paste-buffer", "delete-buffer"}))

    result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result == "delivery-failed"


@dataclass
class Message:
    """The parts of an MQTT message the relay reads."""

    topic: str
    payload: bytes


@dataclass
class FakeClient:
    """Records what the relay asks its MQTT client to do."""

    subscriptions: list[tuple[str, int]] = field(default_factory=list)
    published: list[tuple[str, str, int]] = field(default_factory=list)
    connections: list[tuple[str, int, int]] = field(default_factory=list)
    loops: list[bool] = field(default_factory=list)
    disconnects: int = 0

    def subscribe(self, topic: str, qos: int = 0) -> None:
        """Record a subscription.

        Args:
            topic: The topic filter.
            qos: The requested QoS.
        """
        self.subscriptions.append((topic, qos))

    def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        """Record a publication.

        Args:
            topic: The topic.
            payload: The payload.
            qos: The QoS.
        """
        self.published.append((topic, payload, qos))

    def connect_async(self, host: str, port: int, keepalive: int) -> None:
        """Record a connection request.

        Args:
            host: The broker host.
            port: The broker port.
            keepalive: The keepalive in seconds.
        """
        self.connections.append((host, port, keepalive))

    def loop_forever(self, retry_first_connection: bool) -> None:  # noqa: FBT001
        """Record the loop starting, then end it as an interrupt would.

        Args:
            retry_first_connection: Whether the first connection is retried.

        Raises:
            KeyboardInterrupt: Always.
        """
        self.loops.append(retry_first_connection)
        raise KeyboardInterrupt

    def disconnect(self) -> None:
        """Record a disconnect."""
        self.disconnects += 1


@dataclass
class Deliveries:
    """Stands in for pasting into a pane, recording each attempt."""

    reason: str | None = None
    calls: list[tuple[PaneTarget, str, str]] = field(default_factory=list)

    def __call__(self, target: PaneTarget, message_id: str, text: str) -> str | None:
        """Record a delivery attempt.

        Args:
            target: The pane.
            message_id: The prompt's identifier.
            text: The prompt.

        Returns:
            The configured failure reason, or ``None`` for success.
        """
        self.calls.append((target, message_id, text))
        return self.reason


def prompt_message(
    agent: str = "codex",
    session_id: str = "s",
    payload: str | None = None,
    kind: str = PROMPT_KIND,
) -> Message:
    """Build the message a dashboard publishes for a prompt.

    Args:
        agent: The agent name.
        session_id: The session identity.
        payload: The payload, defaulting to a valid prompt with id ``id-1``.
        kind: The topic kind.

    Returns:
        The message.
    """
    body = format_prompt("id-1", "hello") if payload is None else payload
    return Message(session_topic(agent, session_id, kind), body.encode())


@pytest.fixture
def deliveries() -> Deliveries:
    """Return a delivery recorder that reports success.

    Returns:
        The recorder.
    """
    return Deliveries()


@pytest.fixture
def prompt_relay(deliveries: Deliveries) -> relay.PromptRelay:
    """Create a relay that delivers through the recorder and a fake client.

    Args:
        deliveries: The delivery recorder.

    Returns:
        The relay.
    """
    prompt_relay = relay.PromptRelay("broker", 1883, 60, deliver=deliveries)
    prompt_relay.client = FakeClient()  # type: ignore[assignment]
    return prompt_relay


def receive(prompt_relay: relay.PromptRelay, message: Message) -> None:
    """Give the relay a message the way its MQTT client would.

    Args:
        prompt_relay: The relay.
        message: The message.
    """
    prompt_relay._on_message(prompt_relay.client, None, message)  # type: ignore[arg-type]


def published(prompt_relay: relay.PromptRelay) -> FakeClient:
    """Return the fake client of a relay.

    Args:
        prompt_relay: The relay.

    Returns:
        Its client, typed as the fake.
    """
    client = prompt_relay.client
    assert isinstance(client, FakeClient)
    return client


def test_relay_delivers_a_prompt_for_a_known_session_and_acknowledges(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """A prompt for a recorded session is typed and acknowledged as delivered.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    panes.record_pane("Codex", "native:1", {"TMUX_PANE": "%3"})

    receive(prompt_relay, prompt_message("Codex", "native:1"))

    assert deliveries.calls == [(PaneTarget("%3", None, None), "id-1", "hello")]
    ((topic, payload, qos),) = published(prompt_relay).published
    assert topic == session_topic("codex", "native:1", ACK_KIND)
    assert qos == 1
    assert parse_ack(payload.encode()) == {"id": "id-1", "status": "delivered"}


def test_relay_acknowledges_a_failed_delivery(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """A delivery failure is reported with its reason.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})
    deliveries.reason = "pane-unavailable"

    receive(prompt_relay, prompt_message())

    ((_, payload, _),) = published(prompt_relay).published
    assert parse_ack(payload.encode()) == {
        "id": "id-1",
        "status": "failed",
        "reason": "pane-unavailable",
    }


def test_relay_ignores_sessions_it_does_not_know(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """Another machine's relay answers for its own sessions; this one stays silent.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    receive(prompt_relay, prompt_message(session_id="elsewhere"))

    assert deliveries.calls == []
    assert published(prompt_relay).published == []


def test_relay_types_a_repeated_prompt_only_once(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """A QoS 1 redelivery doesn't submit the prompt twice.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})

    receive(prompt_relay, prompt_message())
    receive(prompt_relay, prompt_message())

    assert len(deliveries.calls) == 1
    assert len(published(prompt_relay).published) == 1


def test_relay_forgets_old_message_ids(prompt_relay: relay.PromptRelay) -> None:
    """The record of handled prompts stays bounded.

    Args:
        prompt_relay: The relay under test.
    """
    for number in range(relay._SEEN_LIMIT + 1):
        assert prompt_relay._is_duplicate(("codex", "s", str(number))) is False

    assert len(prompt_relay._seen) == relay._SEEN_LIMIT
    assert prompt_relay._is_duplicate(("codex", "s", "0")) is False


def test_relay_drops_invalid_prompts(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """A malformed prompt is never typed.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})

    receive(prompt_relay, prompt_message(payload="not json"))

    assert deliveries.calls == []


def test_relay_ignores_other_topics_and_acknowledgments(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """Only prompt topics are acted on, even if the subscription is wider.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})

    receive(prompt_relay, Message("vauxhall/agents/codex/activity", b"{}"))
    receive(prompt_relay, prompt_message(kind=ACK_KIND))

    assert deliveries.calls == []


def test_relay_subscribes_to_prompts_at_qos_one_on_connect(
    prompt_relay: relay.PromptRelay,
) -> None:
    """A reconnect subscribes again, and a refused connection does not.

    Args:
        prompt_relay: The relay under test.
    """
    client = FakeClient()

    prompt_relay._on_connect(client, None, None, 0, None)  # type: ignore[arg-type]
    prompt_relay._on_connect(client, None, None, 5, None)  # type: ignore[arg-type]

    assert client.subscriptions == [("vauxhall/agents/+/sessions/+/prompt", 1)]


def test_relay_run_retries_the_first_connection_and_disconnects(
    prompt_relay: relay.PromptRelay,
) -> None:
    """Starting before the broker is up is fine; stopping disconnects.

    Args:
        prompt_relay: The relay under test.
    """
    prompt_relay.run()

    client = published(prompt_relay)
    assert client.connections == [("broker", 1883, 60)]
    assert client.loops == [True]
    assert client.disconnects == 1
