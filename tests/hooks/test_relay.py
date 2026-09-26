# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the tmux prompt relay."""

import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest

from vauxhall.core.prompts import (
    ACK_KIND,
    PROMPT_KIND,
    format_prompt,
    parse_ack,
    session_topic,
)
from vauxhall.hooks import config as hook_config
from vauxhall.hooks import panes, relay
from vauxhall.hooks.panes import PaneTarget

TARGET = PaneTarget("%3", "/run/tmux-1000/default", 4242)


class FakeTmux:
    """Records tmux commands and answers like a healthy server."""

    def __init__(self, server_pid: str = "4242", fail_on: str | None = None) -> None:
        """Create the fake.

        Args:
            server_pid: What ``display-message`` reports as the server PID.
            fail_on: A tmux command that should fail.
        """
        self.commands: list[list[str]] = []
        self.inputs: list[bytes | None] = []
        self.server_pid = server_pid
        self.fail_on = fail_on

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> "subprocess.CompletedProcess[bytes]":
        """Run a fake tmux command.

        Args:
            command: The command line.
            **kwargs: The ``subprocess.run`` options, of which only ``input`` matters.

        Returns:
            A completed process.

        Raises:
            subprocess.CalledProcessError: For the command set to fail.
        """
        self.commands.append(command)
        self.inputs.append(kwargs.get("input"))
        assert kwargs["check"] is True
        assert kwargs["timeout"] == relay.TMUX_TIMEOUT_SECONDS
        name = command[3]
        if name == self.fail_on:
            raise subprocess.CalledProcessError(1, command)
        stdout = f"{self.server_pid}\n".encode() if name == "display-message" else b""
        return subprocess.CompletedProcess(command, 0, stdout, b"")


def test_deliver_pastes_the_text_and_submits() -> None:
    """The prompt is pasted as a bracketed paste, then Enter is sent."""
    tmux = FakeTmux()
    sleeps: list[float] = []

    result = relay.deliver_prompt(
        TARGET, "id-1", "line one\nline two", tmux, sleeps.append
    )

    assert result is None
    names = [command[3] for command in tmux.commands]
    assert names == ["display-message", "load-buffer", "paste-buffer", "send-keys"]
    assert all(
        command[:3] == ["tmux", "-S", TARGET.socket] for command in tmux.commands
    )
    load, paste, keys = tmux.commands[1:]
    assert tmux.inputs[1] == b"line one\nline two"
    assert "-p" in paste
    assert paste[paste.index("-t") + 1] == "%3"
    assert paste[paste.index("-b") + 1] == load[load.index("-b") + 1]
    assert keys[-3:] == ["-t", "%3", "Enter"]
    assert sleeps == [relay.SUBMIT_DELAY_SECONDS]


def test_deliver_never_passes_the_text_on_the_command_line() -> None:
    """Prompt text reaches tmux only through standard input."""
    tmux = FakeTmux()

    relay.deliver_prompt(TARGET, "id-1", "; rm -rf ~ #{pid}", tmux, lambda _: None)

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
    assert [command[3] for command in tmux.commands] == ["display-message"]


def test_deliver_reports_a_missing_pane() -> None:
    """A pane tmux no longer knows is unavailable."""
    result = relay.deliver_prompt(
        TARGET, "id-1", "hi", FakeTmux(fail_on="display-message"), lambda _: None
    )

    assert result == "pane-unavailable"


def test_deliver_reports_a_missing_tmux() -> None:
    """A machine without tmux cannot deliver."""

    def missing(*_: object, **__: object) -> "subprocess.CompletedProcess[bytes]":
        """Fail like a missing executable.

        Raises:
            FileNotFoundError: Always.
        """
        raise FileNotFoundError

    assert relay.deliver_prompt(TARGET, "id-1", "hi", missing) == "pane-unavailable"


@pytest.mark.parametrize("failing", ["load-buffer", "paste-buffer", "send-keys"])
def test_deliver_cleans_up_after_a_failure(failing: str) -> None:
    """A failed step reports failure and removes the temporary buffer.

    Args:
        failing: The tmux command that fails.
    """
    tmux = FakeTmux(fail_on=failing)

    result = relay.deliver_prompt(TARGET, "id-1", "hi", tmux, lambda _: None)

    assert result == "delivery-failed"
    assert tmux.commands[-1][3] == "delete-buffer"


def test_deliver_survives_a_failed_cleanup() -> None:
    """A buffer that cannot be removed doesn't hide the delivery failure."""

    def always_fail_after_display(
        command: list[str], **_: object
    ) -> "subprocess.CompletedProcess[bytes]":
        """Answer the pid check, then fail everything.

        Args:
            command: The command line.
            **_: Ignored ``subprocess.run`` options.

        Returns:
            The server PID reply.

        Raises:
            subprocess.CalledProcessError: For every command but the pid check.
        """
        if command[3] == "display-message":
            return subprocess.CompletedProcess(command, 0, b"4242\n", b"")
        raise subprocess.CalledProcessError(1, command)

    result = relay.deliver_prompt(
        TARGET, "id-1", "hi", always_fail_after_display, lambda _: None
    )

    assert result == "delivery-failed"


def make_message(
    agent: str, session_id: str, payload: bytes, kind: str = PROMPT_KIND
) -> MagicMock:
    """Build an MQTT message for a session topic.

    Args:
        agent: The agent name.
        session_id: The session identity.
        payload: The message payload.
        kind: The topic kind.

    Returns:
        A message with a topic and payload.
    """
    message = MagicMock()
    message.topic = session_topic(agent, session_id, kind)
    message.payload = payload
    return message


@pytest.fixture
def prompt_relay() -> relay.PromptRelay:
    """Create a relay whose delivery is a mock that succeeds.

    Returns:
        The relay, with a mock client and delivery function.
    """
    prompt_relay = relay.PromptRelay(
        "broker", 1883, 60, deliver=MagicMock(return_value=None)
    )
    prompt_relay.client = MagicMock()
    return prompt_relay


def published_ack(prompt_relay: relay.PromptRelay) -> tuple[str, dict[str, str]]:
    """Return the topic and content of the one acknowledgment published.

    Args:
        prompt_relay: The relay whose client published it.

    Returns:
        The topic and the parsed acknowledgment.
    """
    ((topic, payload), kwargs) = prompt_relay.client.publish.call_args
    assert kwargs == {"qos": 1}
    ack = parse_ack(payload.encode())
    assert ack is not None
    return topic, ack


def test_relay_delivers_a_prompt_for_a_known_session_and_acknowledges(
    prompt_relay: relay.PromptRelay,
) -> None:
    """A prompt for a recorded session is typed and acknowledged as delivered.

    Args:
        prompt_relay: The relay under test.
    """
    panes.record_pane("Codex", "native:1", {"TMUX_PANE": "%3"})
    message = make_message("Codex", "native:1", format_prompt("id-1", "hello").encode())

    prompt_relay._on_message(prompt_relay.client, None, message)

    prompt_relay.deliver.assert_called_once_with(
        PaneTarget("%3", None, None), "id-1", "hello"
    )  # type: ignore[attr-defined]
    topic, ack = published_ack(prompt_relay)
    assert topic == session_topic("codex", "native:1", ACK_KIND)
    assert ack == {"id": "id-1", "status": "delivered"}


def test_relay_acknowledges_a_failed_delivery(prompt_relay: relay.PromptRelay) -> None:
    """A delivery failure is reported with its reason.

    Args:
        prompt_relay: The relay under test.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})
    prompt_relay.deliver = MagicMock(return_value="pane-unavailable")

    prompt_relay._on_message(
        prompt_relay.client,
        None,
        make_message("codex", "s", format_prompt("id-1", "hi").encode()),
    )

    assert published_ack(prompt_relay)[1] == {
        "id": "id-1",
        "status": "failed",
        "reason": "pane-unavailable",
    }


def test_relay_ignores_sessions_it_does_not_know(
    prompt_relay: relay.PromptRelay,
) -> None:
    """Another machine's relay answers for its own sessions; this one stays silent.

    Args:
        prompt_relay: The relay under test.
    """
    prompt_relay._on_message(
        prompt_relay.client,
        None,
        make_message("codex", "elsewhere", format_prompt("id-1", "hi").encode()),
    )

    prompt_relay.deliver.assert_not_called()  # type: ignore[attr-defined]
    prompt_relay.client.publish.assert_not_called()


def test_relay_types_a_repeated_prompt_only_once(
    prompt_relay: relay.PromptRelay,
) -> None:
    """A QoS 1 redelivery doesn't submit the prompt twice.

    Args:
        prompt_relay: The relay under test.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})
    message = make_message("codex", "s", format_prompt("id-1", "hi").encode())

    prompt_relay._on_message(prompt_relay.client, None, message)
    prompt_relay._on_message(prompt_relay.client, None, message)

    prompt_relay.deliver.assert_called_once()  # type: ignore[attr-defined]
    prompt_relay.client.publish.assert_called_once()


def test_relay_forgets_old_message_ids(prompt_relay: relay.PromptRelay) -> None:
    """The record of handled prompts stays bounded.

    Args:
        prompt_relay: The relay under test.
    """
    for number in range(relay._SEEN_LIMIT + 1):
        assert prompt_relay._is_duplicate(("codex", "s", str(number))) is False

    assert len(prompt_relay._seen) == relay._SEEN_LIMIT
    assert prompt_relay._is_duplicate(("codex", "s", "0")) is False


@pytest.mark.parametrize(
    "payload",
    [b"not json", format_prompt("id-1", "hi").replace("hi", "\\u001b").encode()],
)
def test_relay_drops_invalid_prompts(
    prompt_relay: relay.PromptRelay, payload: bytes
) -> None:
    """Malformed or unsafe prompts are never typed.

    Args:
        prompt_relay: The relay under test.
        payload: An invalid prompt payload.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})

    prompt_relay._on_message(
        prompt_relay.client, None, make_message("codex", "s", payload)
    )

    prompt_relay.deliver.assert_not_called()  # type: ignore[attr-defined]


def test_relay_ignores_other_topics_and_acknowledgments(
    prompt_relay: relay.PromptRelay,
) -> None:
    """Only prompt topics are acted on, even if the subscription is wider.

    Args:
        prompt_relay: The relay under test.
    """
    panes.record_pane("codex", "s", {"TMUX_PANE": "%3"})
    other = MagicMock(topic="vauxhall/agents/codex/activity", payload=b"{}")

    prompt_relay._on_message(prompt_relay.client, None, other)
    prompt_relay._on_message(
        prompt_relay.client,
        None,
        make_message("codex", "s", format_prompt("id-1", "hi").encode(), ACK_KIND),
    )

    prompt_relay.deliver.assert_not_called()  # type: ignore[attr-defined]


def test_relay_subscribes_to_prompts_at_qos_one_on_connect(
    prompt_relay: relay.PromptRelay,
) -> None:
    """A reconnect subscribes again, and a refused connection does not.

    Args:
        prompt_relay: The relay under test.
    """
    client = MagicMock()

    prompt_relay._on_connect(client, None, MagicMock(), 0, None)
    client.subscribe.assert_called_once_with(
        "vauxhall/agents/+/sessions/+/prompt", qos=1
    )

    client.reset_mock()
    prompt_relay._on_connect(client, None, MagicMock(), 5, None)
    client.subscribe.assert_not_called()


def test_relay_run_retries_the_first_connection_and_disconnects(
    prompt_relay: relay.PromptRelay,
) -> None:
    """Starting before the broker is up is fine; stopping disconnects.

    Args:
        prompt_relay: The relay under test.
    """
    prompt_relay.client.loop_forever.side_effect = KeyboardInterrupt

    prompt_relay.run()

    prompt_relay.client.connect_async.assert_called_once_with(
        "broker", 1883, keepalive=60
    )
    prompt_relay.client.loop_forever.assert_called_once_with(
        retry_first_connection=True
    )
    prompt_relay.client.disconnect.assert_called_once_with()


def test_main_runs_a_relay_with_the_hook_broker_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The console script relays over the broker the hooks are configured for.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("VAUXHALL_MQTT_HOST", "broker.example")
    monkeypatch.setenv("VAUXHALL_MQTT_PORT", "1884")
    created: list[Any] = []

    def fake_relay(host: str, port: int, keepalive: int) -> MagicMock:
        """Stand in for the relay class.

        Args:
            host: The broker host.
            port: The broker port.
            keepalive: The keepalive.

        Returns:
            A mock relay.
        """
        created.append((host, port, keepalive))
        return MagicMock()

    monkeypatch.setattr(relay, "PromptRelay", fake_relay)
    monkeypatch.setattr(hook_config, "hook_settings", hook_config.HookConfig.load())

    relay.main()

    assert created == [("broker.example", 1884, 60)]
