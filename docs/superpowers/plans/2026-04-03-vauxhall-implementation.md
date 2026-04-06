# Vauxhall Agent Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time Python/Tkinter dashboard that monitors multiple AI agents via MQTT, showing state, logs, and token metrics with easy "copy-to-clipboard" navigation.

**Architecture:** Producer-Consumer over MQTT (Mosquitto). Hooks (Producers) send JSON telemetry; the Dashboard (Consumer) updates a dynamic list of agent cards in a background-threaded UI.

**Tech Stack:** Python 3.x, Tkinter, `paho-mqtt`, `pyperclip`, `ruff` (linting/formatting).

---

### Task 1: Project Setup & Linting

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `vauxhall/__init__.py`

- [ ] **Step 1: Create `pyproject.toml` with Ruff configuration**
```toml
[project]
name = "vauxhall"
version = "0.1.0"
dependencies = [
    "paho-mqtt>=2.0.0",
    "pyperclip>=1.8.2",
]

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I"]
```

- [ ] **Step 2: Create `requirements.txt`**
```text
paho-mqtt>=2.0.0
pyperclip>=1.8.2
pytest>=7.0.0
ruff>=0.3.0
```

- [ ] **Step 3: Initialize package**
```bash
mkdir -p vauxhall/dashboard vauxhall/hooks/gemini tests
touch vauxhall/__init__.py vauxhall/dashboard/__init__.py vauxhall/hooks/__init__.py
```

- [ ] **Step 4: Commit**
```bash
git add pyproject.toml requirements.txt vauxhall/
git commit -m "chore: initial project structure and linting config"
```

---

### Task 2: Hook Client Library

**Files:**
- Create: `vauxhall/hooks/client.py`
- Create: `tests/test_hook_client.py`

- [ ] **Step 1: Write failing test for message formatting**
```python
import json
from vauxhall.hooks.client import format_message

def test_format_message():
    msg = format_message("Gemini", "/tmp/ws", "Acting", tool="grep")
    data = json.loads(msg)
    assert data["agent"] == "Gemini"
    assert data["state"] == "Acting"
    assert data["details"]["tool"] == "grep"
```

- [ ] **Step 2: Implement `format_message`**
```python
import json

def format_message(agent, workspace, state, **details):
    return json.dumps({
        "agent": agent,
        "workspace": workspace,
        "state": state,
        "details": details
    })
```

- [ ] **Step 3: Implement `TelemetryClient` with MQTT (Non-blocking)**
```python
import paho.mqtt.client as mqtt

class TelemetryClient:
    def __init__(self, host="localhost", port=1883):
        self.host = host
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def send(self, agent, workspace, state, **details):
        payload = format_message(agent, workspace, state, **details)
        topic = f"vauxhall/agents/{agent.lower()}/activity"
        try:
            self.client.connect(self.host, self.port, keepalive=5)
            self.client.publish(topic, payload)
            self.client.disconnect()
        except Exception:
            pass # Fail silently per spec
```

- [ ] **Step 4: Run tests & Commit**
```bash
pytest tests/test_hook_client.py
git add vauxhall/hooks/client.py tests/test_hook_client.py
git commit -m "feat: add telemetry hook client"
```

---

### Task 3: Dashboard MQTT Subscriber

**Files:**
- Create: `vauxhall/dashboard/mqtt_client.py`

- [ ] **Step 1: Implement `DashboardSubscriber`**
```python
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
```

- [ ] **Step 2: Commit**
```bash
git add vauxhall/dashboard/mqtt_client.py
git commit -m "feat: add dashboard mqtt subscriber"
```

---

### Task 4: UI Components (Agent Card)

**Files:**
- Create: `vauxhall/dashboard/ui_components.py`

- [ ] **Step 1: Implement `AgentCard` widget**
```python
import tkinter as tk
from tkinter import ttk
import pyperclip

class AgentCard(ttk.Frame):
    def __init__(self, parent, agent, workspace):
        super().__init__(parent, padding=10, style="Card.TFrame")
        self.agent = agent
        self.workspace = workspace
        
        self.header = ttk.Label(self, text=f"{agent} @ {workspace}", font=("Arial", 10, "bold"))
        self.header.pack(fill="x")
        
        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(self, textvariable=self.status_var)
        self.status_label.pack(fill="x")
        
        self.log_text = tk.Text(self, height=3, state="disabled", bg="#1e1e1e", fg="#d4d4d4")
        self.log_text.pack(fill="x", pady=5)
        
        self.bind("<Button-1>", self._on_click)
        
    def update_data(self, data):
        self.status_var.set(data.get("state", "Unknown"))
        details = data.get("details", {})
        if "tool" in details:
            self._update_log(f"Running: {details['tool']}\n{details.get('cmd', '')}")
        if data.get("state") == "Error":
            self.configure(style="Error.TFrame")
            
    def _update_log(self, text):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", text)
        self.log_text.config(state="disabled")

    def _on_click(self, event):
        pyperclip.copy(f"cd {self.workspace}")
        print(f"Copied to clipboard: cd {self.workspace}")
```

- [ ] **Step 2: Commit**
```bash
git add vauxhall/dashboard/ui_components.py
git commit -m "feat: add agent card UI component"
```

---

### Task 5: Main Dashboard Application

**Files:**
- Create: `vauxhall/dashboard/app.py`

- [ ] **Step 1: Implement `VauxhallApp`**
```python
import tkinter as tk
from tkinter import ttk
from vauxhall.dashboard.ui_components import AgentCard
from vauxhall.dashboard.mqtt_client import DashboardSubscriber

class VauxhallApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vauxhall Agent Dashboard")
        self.geometry("600x800")
        
        self.cards = {} # (agent, workspace) -> AgentCard
        
        self.scroll_canvas = tk.Canvas(self)
        self.scroll_frame = ttk.Frame(self.scroll_canvas)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scroll_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        
        self.mqtt = DashboardSubscriber(self._on_telemetry)
        self.mqtt.start()

    def _on_telemetry(self, data):
        key = (data["agent"], data["workspace"])
        if key not in self.cards:
            card = AgentCard(self.scroll_frame, data["agent"], data["workspace"])
            card.pack(fill="x", padx=10, pady=5)
            self.cards[key] = card
        
        self.cards[key].update_data(data)

if __name__ == "__main__":
    app = VauxhallApp()
    app.mainloop()
```

- [ ] **Step 2: Commit**
```bash
git add vauxhall/dashboard/app.py
git commit -m "feat: implement main dashboard app"
```

---

### Task 6: Gemini Hooks Integration

**Files:**
- Create: `vauxhall/hooks/gemini/pre_command.py`
- Create: `vauxhall/hooks/gemini/post_command.py`

- [ ] **Step 1: Implement `pre_command.py`**
```python
import sys
import os
from vauxhall.hooks.client import TelemetryClient

def main():
    workspace = os.getcwd()
    # Assuming Gemini CLI passes command details via env or args
    cmd = " ".join(sys.argv[1:])
    client = TelemetryClient()
    client.send("Gemini", workspace, "Acting", tool="command", cmd=cmd)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement `post_command.py`**
```python
import os
from vauxhall.hooks.client import TelemetryClient

def main():
    workspace = os.getcwd()
    client = TelemetryClient()
    client.send("Gemini", workspace, "Idle")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**
```bash
git add vauxhall/hooks/gemini/
git commit -m "feat: add Gemini CLI hooks"
```

---

### Task 7: Final Verification & Simulation Script

**Files:**
- Create: `scripts/simulate_agent.py`

- [ ] **Step 1: Create simulation script**
```python
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
```

- [ ] **Step 2: Run verification**
1. Start Mosquitto broker: `mosquitto`
2. Run Dashboard: `python3 -m vauxhall.dashboard.app`
3. Run Simulation: `python3 scripts/simulate_agent.py`
4. Verify UI updates and "Copy" behavior.

- [ ] **Step 3: Commit**
```bash
git add scripts/simulate_agent.py
git commit -m "test: add agent simulation script for verification"
```
