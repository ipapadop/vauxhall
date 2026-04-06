import json
import paho.mqtt.client as mqtt
import time

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883)
data = {"agent": "Gemini-1.5-Pro", "workspace": "/tmp/vauxhall-test", "state": "Thinking", "details": {"tool": "search", "cmd": "ls"}}
client.publish("vauxhall/agents/test/activity", json.dumps(data))
client.disconnect()
print("Published test message.")
