# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the simulation script."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.simulate_agent import LIFECYCLE_OPERATIONS, simulate_agent
from vauxhall.core.telemetry import telemetry_validation_error


@patch("scripts.simulate_agent.TelemetryClient")
def test_simulate_agent_success(mock_client_class: MagicMock) -> None:
    """Verify simulate_agent publishes expected payload."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.__enter__.return_value = mock_client
    mock_client_class.return_value = mock_client

    simulate_agent(1, 1)

    mock_client_class.assert_called_once_with("localhost", 1883)
    mock_client.send.assert_called_once()

    # Check payload structure
    _args, kwargs = mock_client.send.call_args

    assert kwargs["agent"] == "Gemini-1.5-Pro-1"
    assert kwargs["session_id"] == "simulation:1"
    assert "workspace" in kwargs
    assert "state" in kwargs


@patch("scripts.simulate_agent.TelemetryClient")
def test_simulate_agent_connection_error(mock_client_class: MagicMock) -> None:
    """Verify simulate_agent handles connection error gracefully."""
    mock_client = MagicMock()
    mock_client.is_connected = False
    mock_client.__enter__.return_value = mock_client
    mock_client_class.return_value = mock_client

    simulate_agent(2, 1)

    mock_client.send.assert_not_called()


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS)
def test_simulate_agent_publishes_valid_lifecycle_operations(
    operation: dict,
) -> None:
    """Lifecycle hook operations must be simulated as valid telemetry."""
    with (
        patch("scripts.simulate_agent.TelemetryClient") as mock_client_class,
        patch("scripts.simulate_agent.random.choice", side_effect=["local", operation]),
        patch("scripts.simulate_agent.time.sleep"),
    ):
        mock_client = mock_client_class.return_value
        mock_client.is_connected = True
        mock_client.__enter__.return_value = mock_client
        simulate_agent(1, 1)

    kwargs = mock_client.send.call_args.kwargs
    identity = {"agent", "workspace", "session_id", "state", "env"}
    payload = {
        "schema_version": 1,
        **{key: kwargs[key] for key in identity},
        "details": {key: value for key, value in kwargs.items() if key not in identity},
    }
    assert kwargs["state"] == operation["state"]
    assert operation["details"].items() <= payload["details"].items()
    assert telemetry_validation_error(payload) is None
