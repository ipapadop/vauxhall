# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Simulation script for AI agent activity.

This script publishes mock telemetry data to an MQTT broker to simulate
multiple agents performing various operations. It is used for testing
the Vauxhall Dashboard without requiring real agent hooks.
"""

import argparse
import json
import random
import tempfile
import threading
import time
from pathlib import Path
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
        agent_idx: The index of the agent being simulated (used for unique naming).
        transitions: The number of event transitions to simulate for this agent.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect("localhost", 1883)
    except Exception:
        logger.exception("Agent-%d could not connect to broker", agent_idx)
        return

    agent_id = f"test-{agent_idx}"
    topic = f"vauxhall/agents/{agent_id}/activity"
    agent_name = f"Gemini-1.5-Pro-{agent_idx}"
    workspace = str(Path(tempfile.gettempdir()) / f"vauxhall-test-{agent_idx}")

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
        logger.info(
            "Agent %s published transition %d/%d: %s",
            agent_name,
            i + 1,
            transitions,
            op["state"],
        )
        time.sleep(1)

    client.disconnect()
    logger.info("Agent %s finished %d transitions.", agent_name, transitions)


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Simulate multi-agent activity for Vauxhall"
    )
    parser.add_argument(
        "-n",
        "--num-agents",
        type=int,
        default=1,
        help="Number of concurrent agents to simulate",
    )
    parser.add_argument(
        "-t",
        "--num-transitions",
        type=int,
        default=5,
        help="Number of telemetry events to send per agent",
    )
    args = parser.parse_args()

    logger.info(
        "Starting simulation for %d agent(s) with %d transitions each...",
        args.num_agents,
        args.num_transitions,
    )
    threads = []
    for i in range(args.num_agents):
        # Each agent runs in its own thread to simulate concurrent activity
        t = threading.Thread(target=simulate_agent, args=(i + 1, args.num_transitions))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    logger.info("Finished simulating %d agent(s).", args.num_agents)
