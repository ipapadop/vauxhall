"""Simulation script for AI agent activity.

This script publishes mock telemetry data to an MQTT broker to simulate
multiple agents performing various operations. It is used for testing
the Vauxhall Dashboard without requiring real agent hooks.
"""

import argparse
import json
import random
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

POSSIBLE_OPERATIONS: list[dict[str, Any]] = [
    {
        "state": "Thinking",
        "details": {"thought": "Analyzing the directory structure..."},
    },
    {"state": "Acting", "details": {"tool": "run_shell_command", "cmd": "ls -al"}},
    {"state": "Acting", "details": {"tool": "view_file", "path": "src/main.py"}},
    {
        "state": "Waiting for Input",
        "details": {"prompt": "Shall I proceed with the deletion? [y/n]"},
    },
    {"state": "Error", "details": {"error": "Connection reset by peer"}},
    {
        "state": "Waiting",
        "details": {"status": "Waiting for background task to complete"},
    },
]


def simulate_agent(agent_idx: int) -> None:
    """Simulate a single agent's activity.

    Connects to the MQTT broker, chooses random operations, and publishes
    telemetry messages at regular intervals.

    Args:
        agent_idx: The index of the agent being simulated.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect("localhost", 1883)

    agent_id = f"test-{agent_idx}"
    topic = f"vauxhall/agents/{agent_id}/activity"
    agent_name = f"Gemini-1.5-Pro-{agent_idx}"
    workspace = f"/tmp/vauxhall-test-{agent_idx}"

    for _ in range(5):
        op = random.choice(POSSIBLE_OPERATIONS)
        payload = {
            "agent": agent_name,
            "workspace": workspace,
            "state": op["state"],
            "details": op["details"],
        }
        client.publish(topic, json.dumps(payload))
        time.sleep(2)

    client.disconnect()
    print(f"Agent {agent_name} finished 5 transitions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate agents activity")
    parser.add_argument(
        "-n", "--num-agents", type=int, default=1, help="Number of agents to simulate"
    )
    args = parser.parse_args()

    threads = []
    for i in range(args.num_agents):
        t = threading.Thread(target=simulate_agent, args=(i + 1,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print(f"Finished simulating {args.num_agents} agent(s).")
