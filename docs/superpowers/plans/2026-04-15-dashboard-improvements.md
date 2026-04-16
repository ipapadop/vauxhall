# Dashboard Resilience, Interactivity, and Smooth Transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve MQTT resilience with status updates, add interactive history filtering, and implement smooth FLIP grid transitions.

**Architecture:** 
- Backend: Refactor `DashboardSubscriber` to emit status changes via IPC to the frontend.
- Frontend (History): Add keyword and state filtering to the history modal.
- Frontend (Grid): Implement FLIP (First, Last, Invert, Play) animation technique for smooth agent card re-sorting.

**Tech Stack:** Python (paho-mqtt, pyloid), JavaScript (Vanilla, FLIP), CSS.

---

### Task 1: Backend Resilience & Status Updates

**Files:**
- Modify: `vauxhall/dashboard/mqtt_client.py`
- Modify: `vauxhall/dashboard/app.py`
- Modify: `tests/test_dashboard_mqtt.py`

- [ ] **Step 1: Update `DashboardSubscriber` to support status callbacks**

Modify `vauxhall/dashboard/mqtt_client.py`:
```python
class DashboardSubscriber:
    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None],
        status_callback: Callable[[str], None],  # Add this
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.callback = callback
        self.status_callback = status_callback # Add this
        # ... (rest unchanged)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self.status_callback("Connected to Agent Fleet")
            client.subscribe("vauxhall/agents/+/activity")
            # ...
        else:
            self.status_callback(f"Connection Failed: {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self.status_callback("Disconnected. Retrying...")
```

- [ ] **Step 2: Update `DashboardApp` to forward status to frontend**

Modify `vauxhall/dashboard/app.py`:
```python
    def on_status(message: str) -> None:
        """Handle status updates from MQTT."""
        try:
            if ipc.is_ready:
                window.invoke("status-update", message)
        except Exception as e:
            logger.exception(f"Error in on_status: {e}")

    mqtt = DashboardSubscriber(on_telemetry, on_status)
```

- [ ] **Step 3: Update `tests/test_dashboard_mqtt.py` to verify status callbacks**

```python
def test_dashboard_subscriber_on_connect_status() -> None:
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    
    subscriber._on_connect(MagicMock(), None, {}, 0, None)
    status_callback.assert_called_with("Connected to Agent Fleet")

def test_dashboard_subscriber_on_disconnect_status() -> None:
    status_callback = MagicMock()
    subscriber = DashboardSubscriber(MagicMock(), status_callback)
    
    subscriber._on_disconnect(MagicMock(), None, {}, 1, None)
    status_callback.assert_called_with("Disconnected. Retrying...")
```

- [ ] **Step 4: Run tests**
Run: `.vauxhall-venv/bin/python3 -m pytest tests/test_dashboard_mqtt.py`
Expected: PASS

- [ ] **Step 5: Commit**
`git add vauxhall/dashboard/mqtt_client.py vauxhall/dashboard/app.py tests/test_dashboard_mqtt.py && git commit -m "feat(backend): add MQTT status reporting"`

---

### Task 2: Frontend Status & Interactive History

**Files:**
- Modify: `vauxhall/dashboard/ui/index.html`
- Modify: `vauxhall/dashboard/ui/js/ipc.js`
- Modify: `vauxhall/dashboard/ui/app.js`
- Modify: `vauxhall/dashboard/ui/js/ui.js`
- Modify: `vauxhall/dashboard/ui/style.css`

- [ ] **Step 1: Add Search and Filter UI to Modal**

Modify `vauxhall/dashboard/ui/index.html`:
```html
<div class="modal-header">
    <div style="display: flex; flex-direction: column; gap: 5px; flex: 1;">
        <h2 id="modal-agent-name">Agent History</h2>
        <div class="modal-toolbar" style="display: flex; gap: 10px;">
            <input type="text" id="modal-search" placeholder="Filter history logs..." class="search-bar" style="flex: 1; min-width: 0;">
            <select id="modal-state-filter" class="secondary-btn">
                <option value="ALL">All States</option>
                <option value="Acting">Acting</option>
                <option value="Thinking">Thinking</option>
                <option value="Waiting for Input">Waiting</option>
                <option value="Error">Error</option>
            </select>
        </div>
    </div>
    <span class="close-btn" title="Close history">&times;</span>
</div>
```

- [ ] **Step 2: Update `ipc.js` to listen for `status-update`**

Modify `vauxhall/dashboard/ui/js/ipc.js`:
```javascript
export function initIPC(callbacks) {
    // ...
    if (pyloidEvent && pyloidEvent.listen) {
        pyloidEvent.listen('agent-update', callbacks.onAgentUpdate);
        pyloidEvent.listen('status-update', callbacks.onStatusUpdate); // Add this
    }
    // ...
}
```

- [ ] **Step 3: Update `app.js` to handle status and modal events**

Modify `vauxhall/dashboard/ui/app.js`:
```javascript
    // In init()
    const modalSearch = document.getElementById('modal-search');
    const modalFilter = document.getElementById('modal-state-filter');

    if (modalSearch) {
        modalSearch.addEventListener('input', () => {
            if (currentHistoryKey) openHistoryModal(currentHistoryKey, agents, true);
        });
    }

    if (modalFilter) {
        modalFilter.addEventListener('change', () => {
            if (currentHistoryKey) openHistoryModal(currentHistoryKey, agents, true);
        });
    }

    // In initIPC callbacks
    onStatusUpdate: (msg) => {
        if (status) status.innerText = msg;
    },
```

- [ ] **Step 4: Update `ui.js` with filtering logic**

Modify `vauxhall/dashboard/ui/js/ui.js`:
```javascript
export function openHistoryModal(agentKey, agents, isSilent = false) {
    // ...
    const searchTerm = document.getElementById('modal-search')?.value.toLowerCase() || '';
    const stateFilter = document.getElementById('modal-state-filter')?.value || 'ALL';

    const filteredHistory = card.history.filter(item => {
        const matchesSearch = getDetailsString(item.details).toLowerCase().includes(searchTerm);
        const matchesState = stateFilter === 'ALL' || item.state === stateFilter;
        return matchesSearch && matchesState;
    });

    body.innerHTML = filteredHistory.map(item => `
        <div class="history-item">
            <span class="history-time">${item.time}</span>
            <span class="history-state">${item.state}</span>
            <span class="history-details">${getDetailsString(item.details)}</span>
        </div>
    `).reverse().join('');
    // ...
}
```

- [ ] **Step 5: Commit**
`git add vauxhall/dashboard/ui/index.html vauxhall/dashboard/ui/js/ipc.js vauxhall/dashboard/ui/app.js vauxhall/dashboard/ui/js/ui.js && git commit -m "feat(ui): add interactive history filtering and status updates"`

---

### Task 3: Smooth Grid Transitions (FLIP)

**Files:**
- Modify: `vauxhall/dashboard/ui/js/ui.js`
- Modify: `vauxhall/dashboard/ui/style.css`

- [ ] **Step 1: Implement FLIP logic in `sortGrid`**

Modify `vauxhall/dashboard/ui/js/ui.js`:
```javascript
export function sortGrid(criteria, grid) {
    const cardsArray = Array.from(grid.children);
    
    // FIRST: Record positions
    const firstPositions = cardsArray.map(card => {
        const rect = card.getBoundingClientRect();
        return { card, top: rect.top, left: rect.left };
    });

    // LAST: Re-sort DOM
    const sorted = cardsArray.sort((a, b) => { /* ... existing logic ... */ });
    grid.innerHTML = '';
    sorted.forEach(card => grid.appendChild(card));

    // INVERT & PLAY
    requestAnimationFrame(() => {
        firstPositions.forEach(({ card, top, left }) => {
            const rect = card.getBoundingClientRect();
            const deltaX = left - rect.left;
            const deltaY = top - rect.top;

            if (deltaX !== 0 || deltaY !== 0) {
                card.style.transition = 'none';
                card.style.transform = `translate(${deltaX}px, ${deltaY}px)`;

                requestAnimationFrame(() => {
                    card.style.transition = 'transform 0.4s ease-out';
                    card.style.transform = '';
                });
            }
        });
    });
}
```

- [ ] **Step 2: Add CSS for smooth transitions**

Modify `vauxhall/dashboard/ui/style.css`:
```css
.agent-card {
    /* ... */
    transition: transform var(--transition-speed), border-color var(--transition-speed),
        opacity var(--transition-speed), filter var(--transition-speed),
        box-shadow var(--transition-speed);
}

.agent-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    border-color: var(--accent-color);
}
```

- [ ] **Step 3: Verification**
- Open the dashboard.
- Run `simulate_agent.py` with 5+ agents.
- Change sorting criteria and verify smooth movement.

- [ ] **Step 4: Commit**
`git add vauxhall/dashboard/ui/js/ui.js vauxhall/dashboard/ui/style.css && git commit -m "feat(ui): implement smooth FLIP transitions for agent grid"`
