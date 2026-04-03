# Vauxhall Agent Dashboard

Vauxhall is a real-time monitoring dashboard for AI agents (Gemini, Claude, Codex, etc.). It provides a centralized view of what your agents are doing across different workspaces, using a lightweight MQTT-based architecture.

## Key Features

- **Real-time Monitoring**: See agent states (Thinking, Acting, Idle, Waiting for Input, Error) as they happen.
- **Detailed Telemetry**: View live logs, active tools, token counts, and operation durations.
- **Multi-Agent Support**: Track multiple agents running in different workspaces simultaneously.
- **Interactive Navigation**: Click any agent card to copy a `cd` command to your clipboard for quick workspace access.
- **Resilient Design**: Non-blocking hooks ensure agent performance is never impacted by dashboard connectivity.
- **Stale Agent Detection**: Automatically identifies and grays out agents that haven't checked in recently.

## Architecture

Vauxhall uses a **Producer-Consumer** pattern over MQTT:

1.  **Hooks (Producers)**: Small Python scripts triggered by agent events that publish telemetry to the MQTT broker.
2.  **Mosquitto (Broker)**: A lightweight message broker that routes telemetry from hooks to the dashboard.
3.  **Dashboard (Consumer)**: A Tkinter-based GUI that subscribes to agent topics and updates the UI in real-time.

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

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
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

### 3. Integrate with Agents (e.g., Gemini CLI)
You can use the provided hooks in `vauxhall/hooks/gemini/` to monitor your Gemini CLI sessions. Add them as `pre-command` and `post-command` hooks in your Gemini configuration.

### 4. Simulation
To see the dashboard in action without running actual agents, use the simulation script:
```bash
python3 scripts/simulate_agent.py
```

## Project Structure

- `vauxhall/dashboard/`: The Tkinter GUI application and MQTT subscriber logic.
- `vauxhall/hooks/`: Reusable telemetry client and agent-specific hook implementations.
- `scripts/`: Utility scripts for simulation and verification.
- `tests/`: Comprehensive test suite for UI and network components.
- `docs/superpowers/specs/`: Detailed design and architecture documentation.

## License
MIT
