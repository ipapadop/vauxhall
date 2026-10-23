# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Simulation script for AI agent activity.

This script publishes mock telemetry data to an MQTT broker to simulate
multiple agents performing various operations. It is used for testing
the Vauxhall Dashboard without requiring real agent hooks.
"""

import argparse
import random
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from vauxhall.core.config import MQTTConfig
from vauxhall.core.logging import get_logger, setup_logging
from vauxhall.hooks.client import publish

logger = get_logger(__name__)

POSSIBLE_OPERATIONS: list[dict[str, Any]] = [
    {
        "state": "Thinking",
        "details": {"thought": "Analyzing the directory structure..."},
    },
    {"state": "Acting", "details": {"tool": "run_shell_command", "cmd": "ls -al"}},
    {"state": "Acting", "details": {"tool": "read_file", "cmd": "src/main.py"}},
    {
        "state": "Waiting for Input",
        "details": {"prompt": "Shall I proceed with the deletion? [y/n]"},
    },
    {"state": "Error", "details": {"error": "Connection reset by peer"}},
    {
        "state": "Idle",
        "details": {"status": "Waiting for background task to complete"},
    },
    # Operations matching the lifecycle hook events for session restarts,
    # subagents, permission notifications, context compaction, and API failures.
    {"state": "Idle", "details": {"status": "Session resumed"}},
    {"state": "Acting", "details": {"tool": "Agent", "cmd": "Explore"}},
    {"state": "Waiting for Input", "details": {"prompt": "Permission required..."}},
    {"state": "Thinking", "details": {"status": "Compacting context (auto)"}},
    {"state": "Thinking", "details": {"status": "Context compacted"}},
    {
        "state": "Error",
        "details": {"status": "failed", "error": "API error: rate_limit"},
    },
]


def simulate_agent(agent_idx: int, transitions: int) -> None:
    """Simulate a single agent's activity.

    Publishes a random operation every second, stopping at the first one the
    broker doesn't acknowledge.

    Args:
        agent_idx: The index of the agent being simulated (used for unique naming).
        transitions: The number of event transitions to simulate for this agent.
    """
    agent_name = f"Gemini-1.5-Pro-{agent_idx}"
    session_id = f"simulation:{agent_idx}"
    workspace = str(Path(tempfile.gettempdir()) / f"vauxhall-test-{agent_idx}")

    env = random.choice(["local", "remote"])

    broker = MQTTConfig(host="localhost", port=1883)
    for i in range(transitions):
        op = random.choice(POSSIBLE_OPERATIONS)
        event = {
            "agent": agent_name,
            "workspace": workspace,
            "session_id": session_id,
            "state": op["state"],
            "env": env,
            "details": {
                **op["details"],
                "tokens": random.randint(100, 5000),
                "duration": round(random.uniform(0.5, 30.0), 1),
            },
        }
        if not publish([event], broker):
            logger.error("Agent-%d could not publish to the broker", agent_idx)
            return

        logger.info(
            "Agent %s published transition %d/%d: %s",
            agent_name,
            i + 1,
            transitions,
            op["state"],
        )
        time.sleep(1)

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
