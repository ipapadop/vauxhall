<p align="center">
  <a href="https://github.com/ipapadop/vauxhall">
    <img src="vauxhall/dashboard/ui/logo.svg" width="150" alt="Vauxhall Logo">
  </a>
</p>

# Vauxhall Agent Dashboard

Vauxhall is a real-time monitoring dashboard for AI agents (Gemini, Claude, Codex, etc.). It provides a centralized, **modern grid view** of what your agents are doing across different workspaces, using a lightweight MQTT-based architecture and web technologies.

## Key Features

- **Real-time Monitoring**: See agent states (Thinking, Acting, Idle, Waiting for Input, Error) as they happen with color-coded indicators.
- **Modern Grid Layout**: Responsive web-based interface that displays multiple agent cards simultaneously, proportional to your window size.
- **Session-aware Cards**: Dashboard cards are identified by agent, workspace, and session ID, so concurrent sessions for the same agent in one workspace remain distinct.
- **Detailed Telemetry & Metrics**: View live logs, active tools, performance metrics (token counts, operation duration), and environment context (Local vs. Remote).
- **Real-time Activity Log**: A concise, non-scrolling view of the last 5 events per agent with timestamps (`[HH:mm:ss]`).
- **Audit History**: Deep-dive into agent behavior with a **resizable history modal** (🕒) that supports real-time updates and smart auto-scrolling (freezes on hover for easy reading). Each card retains its latest 20 history records.
- **Bounded Active Cards**: The dashboard retains up to 100 active cards by default; when full, a new identity evicts the least-recently-seen card.
- **Advanced Filtering & Sorting**: Quickly find agents using the global search bar or sort by name, status, tokens, or recent activity.
- **Tooltip Support**: Integrated help for all UI elements to guide new users.
- **Interactive Navigation**: Click any agent card to copy its raw workspace path to your clipboard with visual "Copied!" feedback. Vauxhall does not turn untrusted telemetry into a shell command.
- **Codex and Gemini Hooks**: Built-in lifecycle integrations report prompts, tool activity, permission waits, truthful tool outcomes (completion, failure, cancellation, or unavailable result), and idle state without publishing tool-result content. Tool-duration tracking is isolated by session and, when supplied by the agent, tool-call identity.
- **Resilient Design**: Telemetry sends use bounded QoS 1 broker acknowledgments and fail-safe error boundaries, while Codex and Gemini hooks always return valid protocol JSON even when telemetry fails. Importing the reusable client or configuration modules preserves the host application's logging; executable entry points configure Vauxhall logging explicitly.
- **Safe Telemetry Rendering**: Agent-provided values are rendered as text rather than executable markup.
- **Stale Agent Detection**: Automatically identifies inactive agents with a relative "last seen" timer (e.g., "5m ago") and gray-out effect.
- **Interactive Stale Agents**: Even stale agents remain fully interactive, allowing you to scroll their logs and inspect their history.


## Architecture

Vauxhall uses a **Producer-Consumer** pattern over MQTT:

1.  **Hooks (Producers)**: Small Python scripts triggered by agent events that publish telemetry to the MQTT broker. See [AGENTS.md](AGENTS.md) for integration details.
2.  **Mosquitto (Broker)**: A lightweight message broker that routes telemetry from hooks to the dashboard.
3.  **Dashboard (Consumer)**: A **Pyloid-based web application** combining a Python backend (MQTT) with a modern **Vanilla JavaScript** frontend.

## Prerequisites

- **Python 3.10+**

- **Mosquitto MQTT Broker**: Install via your package manager (e.g., `brew install mosquitto` or `sudo apt install mosquitto`).

## Installation

### For Dashboard Users
```bash
pip install "vauxhall[dashboard]"
```

The package supports Python 3.10 and newer on any operating system supported by
its dependencies.

### For Remote Agents (Minimum Dependencies)
```bash
pip install "vauxhall[hooks]"
```
*(This only installs `paho-mqtt` and the core logic)*

## Usage

### 1. Start the MQTT Broker
Ensure Mosquitto is running on your local machine:
```bash
mosquitto
```

### 2. Run the Dashboard
```bash
vauxhall
```

From a source checkout, `uv run vauxhall` starts the same entry point.

### Configuration

Dashboard configuration is loaded from `vauxhall_dashboard.json` in the current
directory, then `~/.config/vauxhall/vauxhall_dashboard.json`. Environment
variables take precedence over file values, which take precedence over the
defaults below. Hooks use the same MQTT and logging fields with
`vauxhall_hooks.json` in the same search paths.

| Section | Field | Environment variable | Default | Valid values |
| --- | --- | --- | --- | --- |
| `mqtt` | `host` | `VAUXHALL_MQTT_HOST` | `localhost` | Non-empty string |
| `mqtt` | `port` | `VAUXHALL_MQTT_PORT` | `1883` | Integer 1–65535 |
| `mqtt` | `keepalive` | `VAUXHALL_MQTT_KEEPALIVE` | `60` | Integer 0–65535 |
| `logging` | `level` | `VAUXHALL_LOGGING_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `dashboard` | `port` | `VAUXHALL_DASHBOARD_PORT` | `8080` | Integer 1–65535 |
| `dashboard` | `debug` | `VAUXHALL_DASHBOARD_DEBUG` | `false` | Boolean (`true`/`false`, `1`/`0`, or `yes`/`no`) |
| `dashboard` | `window_title` | `VAUXHALL_DASHBOARD_WINDOW_TITLE` | `Vauxhall Agent Dashboard` | Non-empty string |
| `dashboard` | `width` | `VAUXHALL_DASHBOARD_WIDTH` | `1000` | Integer 320–16384 |
| `dashboard` | `height` | `VAUXHALL_DASHBOARD_HEIGHT` | `800` | Integer 320–16384 |
| `dashboard` | `stale_threshold` | `VAUXHALL_DASHBOARD_STALE_THRESHOLD` | `120` | Integer 1–86400 seconds |
| `dashboard` | `pending_update_limit` | `VAUXHALL_DASHBOARD_PENDING_UPDATE_LIMIT` | `500` | Integer 1–10000 |
| `dashboard` | `max_active_agents` | `VAUXHALL_DASHBOARD_MAX_ACTIVE_AGENTS` | `100` | Integer 1–1000 |
| `dashboard` | `max_payload_bytes` | `VAUXHALL_DASHBOARD_MAX_PAYLOAD_BYTES` | `65536` | Integer 1024–1048576 bytes |

Configuration is strict: malformed JSON, non-object sections, wrong scalar
types, invalid ranges, and invalid environment values abort dashboard startup
or hook initialization. Errors identify the environment variable or absolute
configuration path, logical field, invalid value, and expected constraint.
MQTT authentication and TLS settings are intentionally deferred to issue #3.

Dashboard MQTT ingestion is bounded before JSON decoding: messages larger than
`max_payload_bytes` (65,536 bytes by default) and malformed messages are
dropped. Accepted telemetry is schema version 1 with non-empty `agent` (128
characters), `workspace` (4,096), `session_id` (256), and supported `state`
(32), plus optional `env` (`local` or `remote`, 16). `details` accepts at most
16 string keys (64 characters each) with scalar values; string values are
limited to 4,096 characters. Before the frontend is ready, the dashboard keeps
only the newest `pending_update_limit` events (500 by default), discarding the
oldest event when the buffer is full. The core protocol validator enforces the
same schema and field limits for the dashboard and built-in telemetry client.

The dashboard reports `Connecting...`, `Connected to Agent Fleet`, retrying
connection failures or disconnects, and `Disconnected` for an intentional
shutdown. MQTT cleanup always runs when the UI loop exits, including on an
exception. The dashboard requires Pyloid 0.27.2 or newer: its `BrowserWindow`
wrapper marshals cross-thread commands through `command_signal` and
`_handle_command`, so MQTT callbacks can safely call `window.invoke()` without
a second queue. Vauxhall does not depend on those private Pyloid symbols at
runtime.

### 3. Integrate with Agents
Vauxhall supports multiple agents through customizable hooks. Install the desired integration in the agent workspace:

```bash
# Codex
vauxhall-install-codex

# Gemini CLI
vauxhall-install-gemini
```

Each installer creates `.vauxhall-venv` and installs the same immutable Vauxhall
release that provided the command. Registered hooks invoke the packaged
telemetry module, so moving or deleting the source checkout does not break
them. The Codex installer writes `.codex/hooks.json`, rejects invalid existing
structures without replacing them, and gives each telemetry handler a
three-second timeout backed by a one-second MQTT connection limit. The Gemini
installer also registers a `SessionEnd` hook. Both integrations publish
normalized tool outcomes only, never arbitrary tool responses. Both
installers shell-quote POSIX paths and use encoded PowerShell commands on
Windows. Open `/hooks` in Codex after installation to review and trust the new
project hooks. See [AGENTS.md](AGENTS.md) for event mappings, protocol references, manual
configuration, and generic-agent integration. Codex and Gemini preserve their
native session identities, so separate native sessions create separate
dashboard cards even when they use the same agent name and workspace.

### Telemetry schema

Vauxhall accepts only telemetry schema version 1. Every payload requires
`schema_version`, `agent`, `workspace`, `session_id`, and `state`.
`session_id` is an opaque value that must remain stable throughout one session
and must be unique among concurrent sessions for the same agent and workspace.
Generic producers should generate one UUID when the session starts and reuse it
for every event:

```python
from uuid import uuid4

from vauxhall.hooks.client import TelemetryClient

session_id = str(uuid4())
client = TelemetryClient(host="localhost", port=1883)
client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    session_id=session_id,
    state="Acting",
    tool="grep",
)
```

Producers in other languages can publish schema-v1 JSON to
`vauxhall/agents/<agent_name>/activity`:

```json
{
  "schema_version": 1,
  "agent": "AgentName",
  "workspace": "/absolute/path/to/workspace",
  "session_id": "0195db69-a702-73dc-a223-7556293f8cba",
  "state": "Acting",
  "details": {}
}
```

The built-in hooks resolve session identity in this order: the agent's native
session ID, a hash of its transcript path, then `VAUXHALL_SESSION_ID`. They skip
an event when none of those sources is available. Unversioned, incomplete, or
unsupported payloads are logged and dropped by the dashboard.

### 4. Simulation
To see the dashboard in action without running actual agents, use the simulation script to publish mock telemetry data for multiple agents:
```bash
python3 scripts/simulate_agent.py -n 5 -t 20
```
*   `-n`, `--num-agents`: Number of concurrent agents to simulate.
*   `-t`, `--num-transitions`: Number of telemetry events (transitions) to send per agent.


## Project Structure

- `vauxhall/dashboard/`: The Pyloid-based dashboard application and its packaged Vanilla JS UI assets.
- `vauxhall/hooks/`: Reusable telemetry client plus Codex and Gemini hook implementations and installers.
- `scripts/`: Utility scripts for simulation and verification.
- `tests/`: Comprehensive test suite for UI and network components.

## Development

Frontend tests require Node.js 20.19 or newer.

Contributors must follow the coding and documentation standards defined in [AGENTS.md](AGENTS.md#development--maintenance-rules). Specifically:
- **Ruff**: Use the project-pinned Ruff version and run `ruff format .` plus `ruff check --fix .` before committing. Python files must retain their SPDX copyright and license headers.
- **Frontend tests**: Run `npm ci` once, then `npm test` after changing dashboard JavaScript.
- **Packaging**: Run `python -m build` and `twine check dist/*` when changing distribution metadata, entry points, or bundled assets.
- **Docs**: Always update `README.md` and `AGENTS.md` after every change.

## License
MIT
