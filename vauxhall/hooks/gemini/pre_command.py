"""Gemini CLI pre-command hook.

This script is triggered before a Gemini CLI command is executed.
It sends a telemetry message to the Vauxhall Dashboard with the "Acting" state.
"""

import os
import sys

from vauxhall.hooks.client import TelemetryClient
from vauxhall.logging_config import setup_logging


def main() -> None:
    """Execute the pre-command hook.

    Collects the current workspace and command arguments, and sends
    telemetry to the Vauxhall Dashboard.
    """
    setup_logging()
    workspace = os.getcwd()
    # Assuming Gemini CLI passes command details via env or args
    cmd = " ".join(sys.argv[1:])
    client = TelemetryClient()
    client.send("Gemini", workspace, "Acting", tool="command", cmd=cmd)


if __name__ == "__main__":
    main()
