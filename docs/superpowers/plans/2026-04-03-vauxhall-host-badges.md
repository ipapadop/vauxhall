# Host/Environment Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distinguish where agents are running (Local vs Remote) using color-coded text badges in the header.

**Architecture:** Extend the MQTT JSON payload with an optional `env` field and implement a fallback guessing mechanism in the frontend based on the workspace path.

**Tech Stack:** JavaScript (Vanilla), CSS3, Python (Hooks & Simulation).

---

### Task 1: UI Styling for Environment Badges

**Files:**
- Modify: `vauxhall/dashboard/ui/style.css`

- [ ] **Step 1: Add environment badge styles**

Add the following to `vauxhall/dashboard/ui/style.css`:
```css
.env-badge {
    font-size: 0.65em;
    padding: 1px 4px;
    border-radius: 3px;
    font-weight: bold;
    color: white;
    text-transform: uppercase;
}

.env-local {
    background-color: #238636; /* Green */
}

.env-remote {
    background-color: #1f6feb; /* Blue */
}
```

- [ ] **Step 2: Commit**

```bash
git add vauxhall/dashboard/ui/style.css
git commit -m "feat: add styles for environment badges"
```

---

### Task 2: Extend Telemetry Client (Python)

**Files:**
- Modify: `vauxhall/hooks/client.py`

- [ ] **Step 1: Update TelemetryClient.send**

Modify `vauxhall/hooks/client.py` to accept an optional `env` argument:
```python
    def send(self, agent: str, workspace: str, state: str, env: str = None, **details: Any) -> None:
        """Send a telemetry message.

        Args:
            agent: The name of the agent.
            workspace: The workspace directory path.
            state: The current state of the agent.
            env: Optional execution environment (local, remote).
            **details: Additional key-value pairs for message details.
        """
        payload_dict = {
            "agent": agent,
            "workspace": workspace,
            "state": state,
            "details": details
        }
        if env:
            payload_dict["env"] = env
            
        payload = json.dumps(payload_dict)
        # ... rest of method ...
```

- [ ] **Step 2: Commit**

```bash
git add vauxhall/hooks/client.py
git commit -m "feat: allow sending optional environment metadata in telemetry"
```

---

### Task 3: Render Environment Badges (JS)

**Files:**
- Modify: `vauxhall/dashboard/ui/app.js`

- [ ] **Step 1: Update createCard to render env badge**

Modify `createCard` in `vauxhall/dashboard/ui/app.js` to include the environment badge with fallback logic:
```javascript
function createCard(data, pyloidIpc) {
    // Fallback detection
    const env = data.env || (data.workspace.startsWith('/home') || data.workspace.match(/^[A-Z]:\\/) ? 'local' : 'remote');
    
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.innerHTML = `
        <div class="agent-header">
            <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="env-badge env-${env}">${env}</span>
                    <div class="agent-name">${data.agent}</div>
                    <div class="metric-badges"></div>
                </div>
                <div class="agent-workspace">${data.workspace}</div>
            </div>
            <div class="status-badge">Idle</div>
        </div>
        <div class="log-area">Ready...</div>
    `;
    // ... rest of function ...
```

- [ ] **Step 2: Commit**

```bash
git add vauxhall/dashboard/ui/app.js
git commit -m "feat: render environment badges with path-based fallback"
```

---

### Task 4: Verify with Simulation

**Files:**
- Modify: `scripts/simulate_agent.py`

- [ ] **Step 1: Update simulation data**

Modify `scripts/simulate_agent.py` to include random environments:
```python
# In simulate_agent function
    # In simulate_agent function
        envs = ["local", "remote"]
        env = random.choice(envs)

        for _ in range(5):
            # ... choice of op ...
            payload = {
                "agent": agent_name,
                "env": env,
                "workspace": workspace,
                # ... rest of payload ...
            }

    - [ ] **Step 2: Run verification**

    1. Start dashboard: `python -m vauxhall.dashboard.app`
    2. Run simulator: `python scripts/simulate_agent.py -n 3`
    3. Verify cards show different color-coded environment badges (LOCAL, REMOTE).


- [ ] **Step 3: Commit**

```bash
git add scripts/simulate_agent.py
git commit -m "test: update simulator to include environment metadata"
```
