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
- **SVG Sparklines**: Visualize token usage trends over the last 20 operations directly in the card body.
- **Real-time Activity Log**: A concise, non-scrolling view of the last 5 events per agent with timestamps (`[HH:mm:ss]`).
- **Audit History**: Deep-dive into agent behavior with a **resizable history modal** (🕒) that supports real-time updates and smart auto-scrolling (freezes on hover for easy reading).
- **Advanced Filtering & Sorting**: Quickly find agents using the global search bar or sort by name, status, tokens, or recent activity.
- **Tooltip Support**: Integrated help for all UI elements to guide new users.
- **Interactive Navigation**: Click any agent card to copy a `cd` command to your clipboard for quick workspace access with visual "Copied!" feedback.
- **Resilient Design**: Non-blocking hooks and robust backend error boundaries ensure stability without impacting agent performance.
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

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/ipapadop/vauxhall.git
    cd vauxhall
    ```

2.  **Set up a virtual environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Python dependencies**:
    ```bash
    pip install .
    ```

## Usage

### 1. Start the MQTT Broker
Ensure Mosquitto is running on your local machine:
```bash
mosquitto
```

### 2. Run the Dashboard
```bash
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

- `vauxhall/dashboard/`: The Pyloid-based dashboard application (Python logic + Vanilla JS UI).
- `vauxhall/hooks/`: Reusable telemetry client and agent-specific hook implementations.
- `scripts/`: Utility scripts for simulation and verification.
- `tests/`: Comprehensive test suite for UI and network components.
- `docs/superpowers/specs/`: Detailed design and architecture documentation.

## Development

Contributors must follow the coding and documentation standards defined in [AGENTS.md](AGENTS.md#development--maintenance-rules). Specifically:
- **Ruff**: Always run `ruff format .` and `ruff check --fix .` before committing.
- **Docs**: Always update `README.md` and `AGENTS.md` after every change.

## License
MIT
