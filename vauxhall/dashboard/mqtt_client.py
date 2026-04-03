import json

import paho.mqtt.client as mqtt


class DashboardSubscriber:
    def __init__(self, callback, host="localhost", port=1883):
        self.callback = callback
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self._on_message
        self.host = host
        self.port = port

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            self.callback(data)
        except Exception:
            pass

    def start(self):
        self.client.connect(self.host, self.port)
        self.client.subscribe("vauxhall/agents/+/activity")
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
