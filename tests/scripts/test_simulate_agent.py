# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the simulation script."""

from unittest.mock import patch

import pytest

from scripts.simulate_agent import POSSIBLE_OPERATIONS, simulate_agent
from vauxhall.core.config import MQTTConfig
from vauxhall.core.telemetry import SCHEMA_VERSION, telemetry_validation_error


def test_simulate_agent_publishes_each_transition() -> None:
    """Each transition is one event for the agent's session on the local broker."""
    with (
        patch("scripts.simulate_agent.publish", return_value=True) as publish,
        patch("scripts.simulate_agent.time.sleep"),
    ):
        simulate_agent(1, 2)

    assert publish.call_count == 2
    (event,), broker = publish.call_args.args
    assert broker == MQTTConfig(host="localhost", port=1883)
    assert event["agent"] == "Gemini-1.5-Pro-1"
    assert event["session_id"] == "simulation:1"


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
