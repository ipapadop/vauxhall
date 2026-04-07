"""Gemini CLI post-command hook.

This script is triggered after a Gemini CLI command is executed.
It sends a telemetry message to the Vauxhall Dashboard with the "Idle" state.
"""

import os

from vauxhall.hooks.client import TelemetryClient


def main() -> None:
    """Execute the post-command hook.

    Collects the current workspace and sends telemetry to the
    Vauxhall Dashboard indicating the agent is now idle.
    """
    workspace = os.getcwd()
    client = TelemetryClient()
    client.send("Gemini", workspace, "Idle")


if __name__ == "__main__":
    main()
