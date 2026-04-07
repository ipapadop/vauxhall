# Agent Integration Guide

Vauxhall is designed to be agent-agnostic. You can integrate any AI agent or CLI tool by sending telemetry messages to the MQTT broker.

## Supported Agents

Currently, Vauxhall includes built-in support or templates for:
- **Gemini CLI**: Full pre/post command hooks.
- **Generic Agents**: Any agent can be simulated or integrated using the `TelemetryClient`.

## Integration Methods

### 1. Using Python Hooks (Recommended)
If your agent supports Python-based hooks or you are wrapping a CLI tool in Python, use the `TelemetryClient`.

```python
from vauxhall.hooks.client import TelemetryClient

client = TelemetryClient(host="localhost", port=1883)

# Send an "Acting" state with tool details
client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    state="Acting",
    tool="grep",
    cmd="grep -r 'TODO' ."
)

# Send an "Idle" state when finished
client.send("MyAgent", "/path/to/project", "Idle")
```

### 2. Manual MQTT (Any Language)
You can publish JSON messages to the following topic structure:
`vauxhall/agents/<agent_name>/activity`

**Message Format:**
```json
{
  "agent": "AgentName",
  "workspace": "/absolute/path/to/workspace",
  "state": "Acting", 
  "details": {
    "tool": "tool_name",
    "cmd": "command executed",
    "tokens": 1234,
    "prompt": "User prompt if waiting",
    "error": "Error message if failed"
  }
}
```

## Supported States & UI Indicators

The dashboard uses the `state` field to color-code agent cards:

| State | UI Color | Description |
| :--- | :--- | :--- |
| `Acting` | 🟢 Green | Agent is currently executing a tool or command. |
| `Thinking` | 🟢 Green | Agent is processing or planning. |
| `Waiting for Input` | 🟡 Yellow | Agent is paused and waiting for user confirmation. |
| `Input Required` | 🟡 Yellow | Same as above. |
| `Error` | 🔴 Red | Agent encountered a fatal error. |
| `Idle` | None | Agent is finished or standby. |

## Specific Agent Instructions

### Gemini CLI
1. Locate your Gemini CLI configuration file.
2. Add the following hooks:
   - **Pre-command**: `python3 path/to/vauxhall/hooks/gemini/pre_command.py`
   - **Post-command**: `python3 path/to/vauxhall/hooks/gemini/post_command.py`

### Custom Agents
For other agents like Claude or Codex, follow the pattern in `vauxhall/hooks/gemini/` or use the `TelemetryClient` directly in your execution loop.
