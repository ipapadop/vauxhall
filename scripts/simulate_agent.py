import time

from vauxhall.hooks.client import TelemetryClient

client = TelemetryClient()
ws = "/home/user/project-alpha"

print("Simulating Gemini activity...")
client.send("Gemini", ws, "Thinking")
time.sleep(2)
client.send("Gemini", ws, "Acting", tool="run_shell_command", cmd="ls -la")
time.sleep(2)
client.send("Gemini", ws, "Waiting for Input", prompt="Proceed with delete? [y/n]")
time.sleep(3)
client.send("Gemini", ws, "Error", error="Connection reset by peer")
