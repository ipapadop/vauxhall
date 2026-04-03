# Design Spec: Vauxhall Agent Dashboard

**Date:** 2026-04-03
**Topic:** Real-time dashboard for monitoring multiple AI agents (Gemini, Claude, Codex, etc.) across different workspaces using MQTT.

## 1. Overview
Vauxhall is a Python-based dashboard that provides a real-time view of agent activities. It uses a producer-consumer architecture over MQTT (Mosquitto) to collect telemetry from agents via hooks and display it in a Tkinter-based GUI.

## 2. Architecture & Data Flow
- **Producers (Hooks):** Python scripts triggered by agent events (e.g., `pre-command`, `post-command`).
- **Broker:** Mosquitto (MQTT) for lightweight, low-latency messaging.
- **Consumer (Dashboard):** Tkinter application subscribing to agent topics.

### Topic Structure
- `vauxhall/agents/<agent_type>/<workspace_hash>/status`: Lifecycle events.
- `vauxhall/agents/<agent_type>/<workspace_hash>/activity`: Detailed telemetry (tool use, logs, tokens, input prompts).

### Message Format (JSON)
```json
{
  "agent": "Gemini",
  "workspace": "/home/user/project",
  "state": "Acting", // "Thinking", "Acting", "Idle", "Waiting for Input", "Error"
  "details": {
    "tool": "run_shell_command",
    "cmd": "tsc --noEmit",
    "tokens": 1245,
    "prompt": "Which version should I use?", // Optional: only for "Waiting for Input" state
    "error": "FatalError: Connection to tool server lost." // Optional: only for "Error" state
  }
}
```

## 3. Component Structure
- **vauxhall.dashboard**: Tkinter app with a scrollable list of agent cards (Detail-First view).
- **vauxhall.hooks.client**: Common Python library for sending telemetry.
- **vauxhall.hooks.gemini**: Specific hook scripts for the Gemini CLI.

## 4. UI Design (Detail-First List)
Each agent card displays:
- Agent type and workspace path.
- Current state (Thinking, Acting, Idle, Waiting for Input, Error) with color indicators.
- Live log snippet of the current operation.
- Metrics: Token count and duration.
- **Navigation (Copy Command):** Clicking the agent card copies a `cd` or `ssh` command to the clipboard to quickly navigate to the agent's workspace.

## 5. Error Handling & Resilience

- **Hooks:** Non-blocking delivery with 200ms timeout; fail silently to avoid impacting agent performance.
- **Dashboard:** Automatic MQTT reconnection; stale agent detection (gray out card after 2 minutes of silence).

## 6. Testing Strategy
- **Unit Tests:** Pytest for MQTT serialization and UI component state.
- **Integration Tests:** Simulated agents with a mock MQTT broker.
- **Manual Verification:** End-to-end test with the dashboard and real/simulated hooks.
