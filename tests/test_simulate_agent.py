# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the simulation script."""

import json
from unittest.mock import MagicMock, patch

from scripts.simulate_agent import simulate_agent

@patch("scripts.simulate_agent.mqtt.Client")
def test_simulate_agent_success(mock_client_class: MagicMock) -> None:
    """Verify simulate_agent publishes expected payload."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    simulate_agent(1, 1)
    
    mock_client.connect.assert_called_once_with("localhost", 1883)
    mock_client.publish.assert_called_once()
    
    # Check payload structure
    args, _ = mock_client.publish.call_args
    topic, payload_str = args
    payload = json.loads(payload_str)
    
    assert topic == "vauxhall/agents/test-1/activity"
    assert payload["agent"] == "Gemini-1.5-Pro-1"
    assert "workspace" in payload
    assert "state" in payload
    assert "details" in payload
    
    mock_client.disconnect.assert_called_once()

@patch("scripts.simulate_agent.mqtt.Client")
def test_simulate_agent_connection_error(mock_client_class: MagicMock) -> None:
    """Verify simulate_agent handles connection error gracefully."""
    mock_client = MagicMock()
    mock_client.connect.side_effect = Exception("Connection refused")
    mock_client_class.return_value = mock_client
    
    simulate_agent(2, 1)
    
    mock_client.connect.assert_called_once()
    mock_client.publish.assert_not_called()
