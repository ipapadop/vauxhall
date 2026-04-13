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

# Send an "Acting" state with tool details, metrics, and environment context
client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    state="Acting",
    env="local", # Optional: "local" or "remote"
    tool="grep",
    cmd="grep -r 'TODO' .",
    tokens=1245,   # Optional: Token count for the operation
    duration=12.4  # Optional: Duration in seconds
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
  "env": "remote", 
  "details": {
    "tool": "tool_name",
    "cmd": "command executed",
    "tokens": 1234,
    "duration": 5.2,
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

## Metadata & Features

### Environment Badges
Vauxhall displays a badge (LOCAL, REMOTE) based on the `env` field. If omitted, the dashboard attempts to guess the environment based on the `workspace` path:
- Paths starting with `/home` or `C:\` default to **LOCAL**.
- Other absolute paths default to **REMOTE**.

### Metrics & Sparklines
If `tokens` or `duration` are provided in the `details` object, they will appear as small badges. Additionally, an **SVG Sparkline** will visualize the trend of the last 20 token counts in the card header.

### Persistent Log Streaming
The `log-area` on each card is a real-time append-only stream. Any update containing a `tool` or `cmd` will append a new line with a timestamp (`[HH:mm:ss]`). The stream maintains a rolling buffer of the last 50 lines.

### Session History
The dashboard automatically maintains a buffer of the last 20 operations per agent. Users can view this history by clicking the 🕒 icon on the card.

## Specific Agent Instructions

### Gemini CLI
1. Locate your Gemini CLI configuration file (usually `.gemini/settings.json`).
2. Register the following hooks calling the telemetry script:
   - **BeforeAgent**: `vauxhall/hooks/gemini/telemetry_hook.py`
   - **AfterAgent**: `vauxhall/hooks/gemini/telemetry_hook.py`
   - **BeforeTool**: `vauxhall/hooks/gemini/telemetry_hook.py`
   - **AfterTool**: `vauxhall/hooks/gemini/telemetry_hook.py`
   - **Notification**: `vauxhall/hooks/gemini/telemetry_hook.py`

