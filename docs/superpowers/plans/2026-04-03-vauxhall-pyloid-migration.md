# Pyloid Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Vauxhall Agent Dashboard from Tkinter to Pyloid with a responsive modern grid UI.

**Architecture:** Python backend with a Pyloid Bridge for RPC and state management. Vanilla HTML/CSS/JS frontend for the grid display.

**Tech Stack:** Pyloid (PySide6/QtWebEngine), Python 3.10+, Vanilla HTML5/CSS3/JavaScript.

---

### Task 1: Environment Setup & Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pyloid to dependencies**

Update `pyproject.toml`:
```toml
dependencies = [
    "paho-mqtt>=2.0.0",
    "pyperclip>=1.8.2",
    "pyloid>=0.1.0",
]
```

Update `requirements.txt`:
```text
paho-mqtt>=2.0.0
pyperclip>=1.8.2
pyloid>=0.1.0
pytest>=7.0.0
ruff>=0.3.0
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: SUCCESS

- [ ] **Step 3: Verify pyloid installation**

Run: `python -c "import pyloid; print(pyloid.__version__)"`
Expected: SUCCESS (version printed)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml requirements.txt
git commit -m "chore: add pyloid dependency"
```

---

### Task 2: Minimal Pyloid App & IPC setup

**Files:**
- Create: `vauxhall/dashboard/ipc.py`
- Modify: `vauxhall/dashboard/app.py`

- [ ] **Step 1: Create the IPC class**

Create `vauxhall/dashboard/ipc.py`:
```python
from pyloid.ipc import PyloidIPC, Bridge

class DashboardIPC(PyloidIPC):
    @Bridge(str, result=bool)
    def copy_to_clipboard(self, text: str) -> bool:
        """Handled in a later task."""
        print(f"IPC received: {text}")
        return True
```

- [ ] **Step 2: Re-implement app.py with Pyloid v0.27.2**

Modify `vauxhall/dashboard/app.py`:
```python
import os
from pyloid import Pyloid
from vauxhall.dashboard.ipc import DashboardIPC

def main():
    app = Pyloid(app_name="Vauxhall Dashboard")
    
    # Create window with IPC
    window = app.create_window(
        title="Vauxhall Agent Dashboard",
        width=1000,
        height=800,
        IPCs=[DashboardIPC()]
    )
    
    # Path to UI files
    ui_dir = os.path.join(os.path.dirname(__file__), "ui")
    index_path = os.path.join(ui_dir, "index.html")
    
    # Ensure UI dir exists
    os.makedirs(ui_dir, exist_ok=True)
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            f.write("<h1>Vauxhall Loading...</h1>")

    window.load_file(index_path)
    window.show_and_focus()
    app.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the minimal app**

Run: `python -m vauxhall.dashboard.app`
Expected: A Pyloid window opens showing "Vauxhall Loading...".

- [ ] **Step 4: Commit**

```bash
git add vauxhall/dashboard/ipc.py vauxhall/dashboard/app.py
git commit -m "feat: initial pyloid app structure with IPC"
```

---

### Task 3: Frontend Skeleton (HTML/CSS)

**Files:**
- Create: `vauxhall/dashboard/ui/index.html`
- Create: `vauxhall/dashboard/ui/style.css`

- [ ] **Step 1: Create index.html**

Create `vauxhall/dashboard/ui/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vauxhall Dashboard</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header>
        <h1>Vauxhall Agent Dashboard</h1>
    </header>
    <main id="agent-grid">
        <!-- Agent cards will be injected here -->
    </main>
    <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create style.css**

Create `vauxhall/dashboard/ui/style.css`:
```css
:root {
    --bg-color: #0d1117;
    --card-bg: #161b22;
    --text-color: #c9d1d9;
    --accent-color: #58a6ff;
    --error-color: #f85149;
    --border-color: #30363d;
}

body {
    background-color: var(--bg-color);
    color: var(--text-color);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    margin: 0;
    padding: 20px;
}

header {
    margin-bottom: 20px;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 10px;
}

#agent-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
}

.agent-card {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 16px;
    transition: transform 0.2s, border-color 0.2s;
    cursor: pointer;
}

.agent-card:hover {
    border-color: var(--accent-color);
    transform: translateY(-2px);
}

.agent-card.error {
    border-left: 4px solid var(--error-color);
}

.agent-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
}

.agent-name {
    font-weight: bold;
    color: var(--accent-color);
}

.agent-workspace {
    font-size: 0.8em;
    color: #8b949e;
    word-break: break-all;
}

.status-badge {
    font-size: 0.75em;
    padding: 2px 8px;
    border-radius: 10px;
    background: #21262d;
    text-transform: uppercase;
}

.log-area {
    background: #010409;
    padding: 8px;
    border-radius: 4px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.85em;
    height: 80px;
    overflow-y: auto;
    white-space: pre-wrap;
}
```

- [ ] **Step 3: Create dummy app.js**

Create `vauxhall/dashboard/ui/app.js`:
```javascript
console.log("Vauxhall JS Loaded");
```

- [ ] **Step 4: Commit**

```bash
git add vauxhall/dashboard/ui/index.html vauxhall/dashboard/ui/style.css vauxhall/dashboard/ui/app.js
git commit -m "feat: frontend skeleton and styling"
```

---

### Task 4: MQTT Integration & Event Emission

**Files:**
- Modify: `vauxhall/dashboard/app.py`

- [ ] **Step 1: Connect MQTT to Pyloid Window**

Modify `vauxhall/dashboard/app.py` to start the MQTT subscriber and emit events to the window:
```python
import os
from pyloid import Pyloid
from vauxhall.dashboard.ipc import DashboardIPC
from vauxhall.dashboard.mqtt_client import DashboardSubscriber

def main():
    app = Pyloid(app_name="Vauxhall Dashboard")
    
    window = app.create_window(
        title="Vauxhall Agent Dashboard",
        width=1000,
        height=800,
        IPCs=[DashboardIPC()]
    )

    # Callback to emit data to JS
    def on_telemetry(data):
        window.invoke("agent-update", data)

    mqtt = DashboardSubscriber(on_telemetry)
    mqtt.start()

    ui_dir = os.path.join(os.path.dirname(__file__), "ui")
    index_path = os.path.join(ui_dir, "index.html")

    window.load_file(index_path)
    window.show_and_focus()
    app.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify MQTT events in logs**

Add a `print` in `app.py`'s `on_telemetry` and run the app. Simulate an agent message.
Run: `python -m vauxhall.dashboard.app`
Expected: MQTT logs show data being emitted via `window.invoke`.

- [ ] **Step 3: Commit**

```bash
git add vauxhall/dashboard/app.py
git commit -m "feat: connect MQTT to pyloid event emission"
```

---

### Task 5: Dynamic Grid Rendering (JS)

**Files:**
- Modify: `vauxhall/dashboard/ui/app.js`

- [ ] **Step 1: Implement agent-update listener**

Modify `vauxhall/dashboard/ui/app.js` (assuming `window.pyloid.event.listen` exists in global scope):
```javascript
const grid = document.getElementById('agent-grid');
const agents = {}; // (agent, workspace) -> DOM element

// Use global pyloid object if not using modules
const pyloidEvent = window.pyloid.event;
const pyloidIpc = window.pyloid.ipc;

pyloidEvent.listen('agent-update', (data) => {
    const key = `${data.agent}:${data.workspace}`;
    let card = agents[key];

    if (!card) {
        card = createCard(data);
        agents[key] = card;
        grid.appendChild(card);
    }

    updateCard(card, data);
});

function createCard(data) {
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.innerHTML = `
        <div class="agent-header">
            <div>
                <div class="agent-name">${data.agent}</div>
                <div class="agent-workspace">${data.workspace}</div>
            </div>
            <div class="status-badge">Idle</div>
        </div>
        <div class="log-area">Ready...</div>
    `;
    
    card.addEventListener('click', () => {
        pyloidIpc.DashboardIPC.copy_to_clipboard(`cd ${data.workspace}`);
    });
    
    return card;
}

function updateCard(card, data) {
    const statusBadge = card.querySelector('.status-badge');
    const logArea = card.querySelector('.log-area');
    
    statusBadge.textContent = data.state;
    
    if (data.state === 'Error') {
        card.classList.add('error');
    } else {
        card.classList.remove('error');
    }

    const details = data.details || {};
    if (details.tool) {
        logArea.textContent = `Running: ${details.tool}\n${details.cmd || ''}`;
    }
}
```

- [ ] **Step 2: Verify UI updates**

Run the app and simulate MQTT messages.
Expected: Cards appear and update in the grid.

- [ ] **Step 3: Commit**

```bash
git add vauxhall/dashboard/ui/app.js
git commit -m "feat: dynamic grid rendering in JS"
```

---

### Task 6: Clipboard Interaction (IPC)

**Files:**
- Modify: `vauxhall/dashboard/ipc.py`

- [ ] **Step 1: Implement real clipboard logic**

Modify `vauxhall/dashboard/ipc.py`:
```python
import pyperclip
from pyloid.ipc import PyloidIPC, Bridge

class DashboardIPC(PyloidIPC):
    @Bridge(str, result=bool)
    def copy_to_clipboard(self, text: str) -> bool:
        """Copies text to the system clipboard."""
        try:
            pyperclip.copy(text)
            print(f"Copied to clipboard: {text}")
            return True
        except Exception as e:
            print(f"Clipboard error: {e}")
            return False
```

- [ ] **Step 2: Test click-to-copy**

Run the app, click a card, and paste into a terminal.
Expected: `cd <workspace>` is pasted.

- [ ] **Step 3: Commit**

```bash
git add vauxhall/dashboard/ipc.py
git commit -m "feat: implement IPC clipboard interaction"
```


---

### Task 7: Cleanup & Removal of Tkinter

**Files:**
- Delete: `vauxhall/dashboard/ui_components.py`
- Modify: `tests/test_dashboard_app.py` (update to skip GUI checks or test bridge)

- [ ] **Step 1: Remove Tkinter files**

Run: `rm vauxhall/dashboard/ui_components.py`
Expected: SUCCESS

- [ ] **Step 2: Update tests**

Modify `tests/test_dashboard_app.py` to remove `tkinter` dependencies and focus on data flow if possible. (Note: Pyloid GUI testing is complex, focus on the Bridge logic).

- [ ] **Step 3: Final Verification**

Run all tests: `pytest`
Run the dashboard: `python -m vauxhall.dashboard.app`
Expected: App runs smoothly, no tkinter imports left.

- [ ] **Step 4: Commit**

```bash
git add vauxhall/dashboard/ui_components.py tests/test_dashboard_app.py
git commit -m "chore: remove legacy tkinter components"
```
