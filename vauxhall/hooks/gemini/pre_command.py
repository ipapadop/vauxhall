import os
import sys

from vauxhall.hooks.client import TelemetryClient


def main():
    workspace = os.getcwd()
    # Assuming Gemini CLI passes command details via env or args
    cmd = " ".join(sys.argv[1:])
    client = TelemetryClient()
    client.send("Gemini", workspace, "Acting", tool="command", cmd=cmd)


if __name__ == "__main__":
    main()
