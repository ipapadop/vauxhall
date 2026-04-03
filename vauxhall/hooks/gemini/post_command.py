import os

from vauxhall.hooks.client import TelemetryClient


def main():
    workspace = os.getcwd()
    client = TelemetryClient()
    client.send("Gemini", workspace, "Idle")


if __name__ == "__main__":
    main()
