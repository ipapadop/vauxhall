# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the simulation script."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from scripts.simulate_agent import POSSIBLE_OPERATIONS, parse_args, simulate_agent
from vauxhall.core.config import MQTTConfig
from vauxhall.core.telemetry import SCHEMA_VERSION, telemetry_validation_error
from vauxhall.hooks.config import hook_settings


def test_simulate_agent_publishes_each_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each transition is one event, sent to the local broker as the hooks would.

    The hooks' credentials and TLS settings still apply; only the address
    changes.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    hooks_mqtt = MQTTConfig(host="remote", port=8883, username="agent", tls=True)
    monkeypatch.setattr(hook_settings, "mqtt", hooks_mqtt)
    with (
        patch("scripts.simulate_agent.publish", return_value=True) as publish,
        patch("scripts.simulate_agent.time.sleep"),
    ):
        simulate_agent(1, 2)

    assert publish.call_count == 2
    (event,), broker = publish.call_args.args
    assert broker == replace(hooks_mqtt, host="localhost", port=1883)
    assert event["agent"] == "Gemini-1.5-Pro-1"
    assert event["session_id"] == "simulation:1"


def test_simulate_agent_publishes_to_the_chosen_broker() -> None:
    """A broker named on the command line replaces the local default."""
    with (
        patch("scripts.simulate_agent.publish", return_value=True) as publish,
        patch("scripts.simulate_agent.time.sleep"),
    ):
        simulate_agent(1, 1, host="broker.test", port=18830)

    _, broker = publish.call_args.args
    assert (broker.host, broker.port) == ("broker.test", 18830)


def test_parse_args_defaults_to_the_local_broker() -> None:
    """Without options one agent sends five events to localhost:1883.

    The hooks' configured broker is never the default, so simulated telemetry
    can't reach a real fleet's dashboard by accident.
    """
    args = parse_args([])

    assert (args.num_agents, args.num_transitions) == (1, 5)
    assert (args.host, args.port) == ("localhost", 1883)


def test_parse_args_reads_the_broker() -> None:
    """--host and --port choose another broker."""
    args = parse_args(["-n", "3", "--host", "broker.test", "--port", "18830"])

    assert args.num_agents == 3
    assert (args.host, args.port) == ("broker.test", 18830)


def test_simulate_agent_stops_when_the_broker_does_not_acknowledge() -> None:
    """An undelivered event ends the agent's simulation."""
    with (
        patch("scripts.simulate_agent.publish", return_value=False) as publish,
        patch("scripts.simulate_agent.time.sleep"),
    ):
        simulate_agent(2, 3)

    publish.assert_called_once()


@pytest.mark.parametrize("operation", POSSIBLE_OPERATIONS)
def test_simulate_agent_publishes_valid_operations(operation: dict) -> None:
    """Every simulated operation must be valid telemetry.

    Args:
        operation: The case's operation.
    """
    with (
        patch("scripts.simulate_agent.publish", return_value=True) as publish,
        patch("scripts.simulate_agent.random.choice", side_effect=["local", operation]),
        patch("scripts.simulate_agent.time.sleep"),
    ):
        simulate_agent(1, 1)

    (event,), _ = publish.call_args.args
    assert event["state"] == operation["state"]
    assert operation["details"].items() <= event["details"].items()
    assert (
        telemetry_validation_error({"schema_version": SCHEMA_VERSION, **event}) is None
    )
