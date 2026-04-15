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

from vauxhall.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

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


def simulate_agent(agent_idx: int, transitions: int) -> None:
    """Simulate a single agent's activity.

    Connects to the MQTT broker, chooses random operations, and publishes
    telemetry messages at regular intervals.

    Args:
        agent_idx: The index of the agent being simulated.
        transitions: The number of transitions to simulate.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect("localhost", 1883)
    except Exception as e:
        logger.error(f"Agent-{agent_idx} could not connect to broker: {e}")
        return

    agent_id = f"test-{agent_idx}"
    topic = f"vauxhall/agents/{agent_id}/activity"
    agent_name = f"Gemini-1.5-Pro-{agent_idx}"
    workspace = f"/tmp/vauxhall-test-{agent_idx}"

    envs = ["local", "remote"]
    env = random.choice(envs)

    for i in range(transitions):
        op = random.choice(POSSIBLE_OPERATIONS)
        payload = {
            "agent": agent_name,
            "env": env,
            "workspace": workspace,
            "state": op["state"],
            "details": {
                **op["details"],
                "tokens": random.randint(100, 5000),
                "duration": round(random.uniform(0.5, 30.0), 1),
            },
        }
        client.publish(topic, json.dumps(payload))
        msg = (
            f"Agent {agent_name} published transition "
            f"{i + 1}/{transitions}: {op['state']}"
        )
        logger.info(msg)
        time.sleep(1)

    client.disconnect()
    logger.info(f"Agent {agent_name} finished {transitions} transitions.")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Simulate agents activity")
    parser.add_argument(
        "-n", "--num-agents", type=int, default=1, help="Number of agents to simulate"
    )
    parser.add_argument(
        "-t",
        "--num-transitions",
        type=int,
        default=5,
        help="Number of transitions per agent",
    )
    args = parser.parse_args()

    start_msg = (
        f"Starting simulation for {args.num_agents} agent(s) "
        f"with {args.num_transitions} transitions each..."
    )
    logger.info(start_msg)
    threads = []
    for i in range(args.num_agents):
        t = threading.Thread(target=simulate_agent, args=(i + 1, args.num_transitions))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    logger.info(f"Finished simulating {args.num_agents} agent(s).")
