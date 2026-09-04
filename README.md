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
- **Detailed Telemetry & Metrics**: View live logs, active tools, performance metrics (token counts, operation duration), and environment context (Local vs. Remote).
- **Real-time Activity Log**: A concise, non-scrolling view of the last 5 events per agent with timestamps (`[HH:mm:ss]`).
- **Audit History**: Deep-dive into agent behavior with a **resizable history modal** (🕒) that supports real-time updates and smart auto-scrolling (freezes on hover for easy reading).
- **Advanced Filtering & Sorting**: Quickly find agents using the global search bar or sort by name, status, tokens, or recent activity.
- **Tooltip Support**: Integrated help for all UI elements to guide new users.
- **Interactive Navigation**: Click any agent card to copy a `cd` command to your clipboard for quick workspace access with visual "Copied!" feedback.
- **Resilient Design**: Telemetry sends use bounded delivery acknowledgments and fail-safe error boundaries, while Gemini hooks always return valid protocol JSON even when telemetry fails.
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
# Using uv (recommended for development)
uv run python3 -m vauxhall.dashboard.app

# Or using standard python
python3 -m vauxhall.dashboard.app
```

### 3. Integrate with Agents
Vauxhall supports multiple agents through customizable hooks. See [AGENTS.md](AGENTS.md) for detailed integration instructions for Gemini CLI and other tools.

### 4. Simulation
To see the dashboard in action without running actual agents, use the simulation script to publish mock telemetry data for multiple agents:
```bash
python3 scripts/simulate_agent.py -n 5 -t 20
```
*   `-n`, `--num-agents`: Number of concurrent agents to simulate.
*   `-t`, `--num-transitions`: Number of telemetry events (transitions) to send per agent.


## Project Structure

- `vauxhall/dashboard/`: The Pyloid-based dashboard application and its packaged Vanilla JS UI assets.
- `vauxhall/hooks/`: Reusable telemetry client and agent-specific hook implementations.
- `scripts/`: Utility scripts for simulation and verification.
- `tests/`: Comprehensive test suite for UI and network components.

## Development

Frontend tests require Node.js 20.19 or newer.

Contributors must follow the coding and documentation standards defined in [AGENTS.md](AGENTS.md#development--maintenance-rules). Specifically:
- **Ruff**: Always run `ruff format .` and `ruff check --fix .` before committing.
- **Frontend tests**: Run `npm ci` once, then `npm test` after changing dashboard JavaScript.
- **Packaging**: Run `python -m build --wheel` when changing distribution metadata or bundled assets.
- **Docs**: Always update `README.md` and `AGENTS.md` after every change.

## License
MIT
