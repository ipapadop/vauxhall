# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the tmux prompt relay."""

import json
import subprocess
from dataclasses import dataclass, field

import pytest

from vauxhall.core.config import MQTTConfig
from vauxhall.core.prompts import (
    ACK_KIND,
    PROMPT_KIND,
    format_prompt,
    parse_ack,
    session_topic,
)
from vauxhall.hooks import panes, relay
from vauxhall.hooks.panes import PaneTarget

TARGET = PaneTarget("%3", "/run/tmux-1000/default", 4242, 500)
TEXT = "line one\nline two; rm -rf ~ #{pid} `x`"


def command_name(command: list[str]) -> str:
    """Return the tmux subcommand of a command line, or ``ps``.

    Args:
        command: The command line, with or without ``-S <socket>``.

    Returns:
        The subcommand name.
    """
    if command[0] == "ps":
        return "ps"
    return command[3] if command[1] == "-S" else command[1]


class FakeTmux:
    """Records tmux and ``ps`` commands and answers like a healthy server."""

    def __init__(
        self,
        server_pid: str = "4242",
        fail_on: frozenset[str] = frozenset(),
        group: str = "500",
    ) -> None:
        """Create the fake.

        Args:
            server_pid: What ``display-message`` reports as the server PID.
            fail_on: The tmux subcommands, or ``ps``, that fail.
            group: What ``ps`` reports as the pane's foreground process group.
        """
        self.commands: list[list[str]] = []
        self.inputs: list[bytes | None] = []
        self.server_pid = server_pid
        self.fail_on = fail_on
        self.group = group

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
        stdout = {
            "display-message": f"{self.server_pid} 100\n".encode(),
            "ps": f"{self.group:>7}\n".encode(),
        }.get(name, b"")
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
        "ps",
        "copy-mode",
        "load-buffer",
        "paste-buffer",
        "copy-mode",
        "send-keys",
    ]
    display, ps, leave, load, paste, _, keys = tmux.commands
    assert all(
        command[:3] == ["tmux", "-S", TARGET.socket]
        for command in tmux.commands
        if command is not ps
    )
    assert display[-1] == "#{pid} #{pane_pid}"
    assert ps == ["ps", "-o", "tpgid=", "-p", "100"]
    # A pane mode would take Enter and drop the paste's brackets.
    assert leave[3:] == ["copy-mode", "-q", "-t", "%3"]
    assert tmux.inputs[3] == TEXT.encode()
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
        PaneTarget("%3", None, None, 500), "id-1", "hi", tmux, lambda _: None
    )

    assert all(
        command[0] == "tmux" and "-S" not in command
        for command in tmux.commands
        if command[0] != "ps"
    )


def test_deliver_refuses_a_pane_of_a_restarted_server() -> None:
    """After a tmux restart the recorded pane id may name an unrelated pane."""
    tmux = FakeTmux(server_pid="9999")

    result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result == "pane-unavailable"
    assert names(tmux) == ["display-message", "ps"]


@pytest.mark.parametrize("group", ["600", "-1"])
def test_deliver_refuses_a_pane_no_longer_running_the_agent(group: str) -> None:
    """Another foreground group means a shell left behind or another program.

    A restarted agent has the same command name as the session's agent, so
    only the process group tells them apart.

    Args:
        group: What ``ps`` reports: another group, or none.
    """
    tmux = FakeTmux(group=group)

    result = relay.deliver_prompt(TARGET, "id-1", "rm -rf ~", tmux, lambda _: None)

    assert result == "pane-unavailable"
    assert names(tmux) == ["display-message", "ps"]


def test_deliver_refuses_when_ps_cannot_read_the_group() -> None:
    """A group that can't be read can't be shown to be the agent's."""
    tmux = FakeTmux(fail_on=frozenset({"ps"}))

    result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result == "pane-unavailable"
    assert names(tmux) == ["display-message", "ps"]


def test_deliver_types_into_the_agent_the_session_started_with(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The pane's foreground group is still the agent's, so it gets the prompt.

    Args:
        caplog: Pytest log capture fixture.
    """
    tmux = FakeTmux()

    with caplog.at_level("WARNING"):
        result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result is None
    assert "send-keys" in names(tmux)
    assert caplog.records == []


@pytest.mark.parametrize(
    "record",
    [
        pytest.param({"pane": "%3", "server_pid": 4242}, id="no-group"),
        pytest.param(
            {"pane": "%3", "server_pid": 4242, "command": "claude"},
            id="command-from-an-older-hook",
        ),
    ],
)
def test_deliver_refuses_a_record_without_a_process_group(
    record: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing shows the pane still runs the agent, so nothing is typed.

    A record from an older hook, or from a ``ps`` without ``tpgid``, has no
    group; the pane may hold the shell an agent left behind.

    Args:
        record: The pane record on disk.
        caplog: Pytest log capture fixture.
    """
    panes.record_pane("claude", "s1", {"TMUX_PANE": "%3"})
    (path,) = panes.panes_directory().glob("*.json")
    path.write_text(json.dumps(record), encoding="utf-8")
    target = panes.load_pane("claude", "s1")
    assert target is not None
    tmux = FakeTmux()

    with caplog.at_level("WARNING"):
        result = relay.deliver_prompt(target, "id-1", "hi", tmux, lambda _: None)

    assert result == "pane-unavailable"
    assert "send-keys" not in names(tmux)
    assert "Not typing into pane %3" in caplog.text
    assert "hi" not in caplog.text


def test_deliver_reports_a_missing_pane() -> None:
    """A pane tmux no longer knows is unavailable."""
    tmux = FakeTmux(fail_on=frozenset({"display-message"}))

    assert relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None) == (
        "pane-unavailable"
    )


def test_deliver_goes_ahead_when_tmux_cannot_leave_a_mode(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A tmux older than 3.1a has no ``copy-mode -q``, which isn't fatal.

    Args:
        caplog: Pytest log capture fixture.
    """
    tmux = FakeTmux(fail_on=frozenset({"copy-mode"}))

    with caplog.at_level("DEBUG"):
        result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result is None
    assert names(tmux)[-1] == "send-keys"
    assert "Could not leave the mode of pane %3" in caplog.text


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
    retain: bool = False


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
    prompt_relay = relay.PromptRelay(MQTTConfig(host="broker"), deliver=deliveries)
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


def test_relay_ignores_a_retained_prompt(
    prompt_relay: relay.PromptRelay, deliveries: Deliveries
) -> None:
    """A retained prompt, replayed on every subscribe, is not typed.

    Args:
        prompt_relay: The relay under test.
        deliveries: The delivery recorder.
    """
    panes.record_pane("Codex", "native:1", {"TMUX_PANE": "%3"})
    message = prompt_message("Codex", "native:1")
    message.retain = True

    receive(prompt_relay, message)

    assert deliveries.calls == []
    assert published(prompt_relay).published == []


def test_relay_ignores_a_retained_prompt_for_another_machine_quietly(
    prompt_relay: relay.PromptRelay, caplog: pytest.LogCaptureFixture
) -> None:
    """Relays sharing a broker don't warn about other machines' retained prompts.

    Args:
        prompt_relay: The relay under test.
        caplog: Pytest log capture fixture.
    """
    message = prompt_message("Codex", "elsewhere")
    message.retain = True

    with caplog.at_level("WARNING"):
        receive(prompt_relay, message)

    assert caplog.records == []


def test_relay_acknowledges_a_delivery_that_raises_and_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An error while delivering is acknowledged as failed and logged.

    Args:
        caplog: Pytest log capture fixture.
    """
    panes.record_pane("Codex", "native:1", {"TMUX_PANE": "%3"})
    attempts: list[str] = []

    def fail_first_delivery(
        _target: PaneTarget, message_id: str, _text: str
    ) -> str | None:
        """Fail the first delivery the way an unforeseen bug would.

        Args:
            _target: The pane.
            message_id: The prompt's identifier.
            _text: The prompt.

        Returns:
            ``None`` for every delivery after the first.

        Raises:
            RuntimeError: On the first delivery.
        """
        attempts.append(message_id)
        if len(attempts) == 1:
            raise RuntimeError
        return None

    prompt_relay = relay.PromptRelay(
        MQTTConfig(host="broker"), deliver=fail_first_delivery
    )
    prompt_relay.client = FakeClient()  # type: ignore[assignment]

    receive(prompt_relay, prompt_message("Codex", "native:1"))
    receive(
        prompt_relay,
        prompt_message("Codex", "native:1", payload=format_prompt("id-2", "again")),
    )

    acks = [
        parse_ack(payload.encode())
        for _, payload, _ in published(prompt_relay).published
    ]
    assert acks == [
        {"id": "id-1", "status": "failed", "reason": "delivery-failed"},
        {"id": "id-2", "status": "delivered"},
    ]
    assert "Could not deliver a prompt to codex" in caplog.text
    assert "hello" not in caplog.text


def test_relay_survives_an_error_before_delivery(
    prompt_relay: relay.PromptRelay, caplog: pytest.LogCaptureFixture
) -> None:
    """An error outside delivery is logged, not raised into paho's loop.

    Args:
        prompt_relay: The relay under test.
        caplog: Pytest log capture fixture.
    """

    class UnreadableMessage:
        """A message whose topic can't be read."""

        retain = False

        @property
        def topic(self) -> str:
            """Fail the way an unforeseen bug would.

            Raises:
                RuntimeError: Always.
            """
            raise RuntimeError

    prompt_relay._on_message(prompt_relay.client, None, UnreadableMessage())  # type: ignore[arg-type]

    assert "Could not handle a prompt message" in caplog.text


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
