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
If `tokens` or `duration` are provided in the `details` object, they will appear as small badges in the **card footer**. Additionally, an **SVG Sparkline** in the card body will visualize the trend of the last 20 token counts.

### Real-Time Activity Log
The `log-area` on each card is a real-time append-only stream of the **last 5 events**. Any update containing a `tool` or `cmd` will append a new line with a timestamp (`[HH:mm:ss]`). This area is non-scrolling to keep the dashboard clean.

### Session History & Audit
The dashboard automatically maintains a full buffer of the last 20 operations per agent. Users can view this history by clicking the **Clock (🕒)** icon in the card footer to open a **resizable modal**. This modal supports real-time updates and includes a "smart auto-scroll" that freezes when you are hovering to allow for easy inspection.

## Specific Agent Instructions

### Gemini CLI
1. Locate your Gemini CLI configuration file (usually `.gemini/settings.json`).
2. Register the unified `telemetry_hook.py` for all supported hook events:

```json
{
  "hooks": {
    "BeforeAgent": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "vauxhall-telemetry",
            "type": "command",
            "command": "python3 /path/to/vauxhall/hooks/gemini/telemetry_hook.py"
          }
        ]
      }
    ],
    "AfterAgent": [...],
    "BeforeTool": [...],
    "AfterTool": [...],
    "Notification": [...]
  }
}
```

The `telemetry_hook.py` script automatically detects the hook type and handles:
- **Thinking**: Triggered `BeforeAgent`.
- **Acting**: Triggered `BeforeTool` (shows tool name and command).
- **Waiting for Input**: Triggered when `ask_user` is called or when a `ToolPermission` notification appears.
- **Idle**: Triggered `AfterAgent` or `AfterTool`.


