# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the simulation script."""

import json
from unittest.mock import MagicMock, patch

from scripts.simulate_agent import simulate_agent

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
    args, kwargs = mock_client.send.call_args
    
    assert kwargs["agent"] == "Gemini-1.5-Pro-1"
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
