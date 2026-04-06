# Design Spec: Vauxhall Dashboard (Pyloid Migration)

**Date:** 2026-04-03
**Topic:** Migrating the real-time agent dashboard from Tkinter to Pyloid for a modern grid-based web UI.

## 1. Overview
Vauxhall is being upgraded from a native Tkinter interface to a web-based dashboard using **Pyloid**. This allows for a more flexible, responsive "Modern Grid" layout while keeping the backend logic in Python.

## 2. Architecture & Data Flow
- **MQTT Consumer (Python):** Continues to run in a background thread, subscribing to agent telemetry.
- **Pyloid Bridge (Python):** Acts as the RPC layer between Python and the Chromium-based frontend.
- **Frontend (Vanilla HTML/JS):** A single-page application that renders agent activity in real-time.

### Updated Data Flow
1. **MQTT Message:** Arrives in `DashboardSubscriber`.
2. **Bridge Emit:** The subscriber calls `bridge.emit('agent-update', data)`.
3. **JS Listener:** `window.pyloid.on('agent-update', ...)` captures the event in the browser.
4. **DOM Update:** Vanilla JS finds the relevant card (or creates a new one) and updates its content.

## 3. Component Structure
The UI components will move from Python (`ui_components.py`) to a new `ui/` directory:

- **`vauxhall/dashboard/app.py`**:
    - Initializes the `Pyloid` app and `Bridge`.
    - Manages the main window and system tray.
    - Integrates the `DashboardSubscriber`.
- **`vauxhall/dashboard/ui/index.html`**:
    - Base skeleton with a `<div id="agent-grid"></div>`.
- **`vauxhall/dashboard/ui/style.css`**:
    - Defines the grid layout: `display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));`.
    - Modern card styling with transitions for state changes.
- **`vauxhall/dashboard/ui/app.js`**:
    - Event handlers for Pyloid signals.
    - Template-based card generation.

## 4. UI Design (Modern Grid)
Each agent card (web component) will feature:
- **Header:** Agent type and truncated workspace path.
- **State Indicator:** Visual badge (Thinking/Acting/Idle/Error) with color-coded borders.
- **Activity Log:** A scrollable, monospaced area for the latest tool/command output.
- **Interactions:**
    - **Click Card:** Calls `bridge.copy_to_clipboard(path)` via Python.
    - **Hover Effect:** Highlights the card to indicate interactivity.

## 5. Migration Strategy
1. **Phase 1: Environment Setup** - Install `pyloid` and verify the basic "Hello World" bridge.
2. **Phase 2: Frontend Skeleton** - Create the static HTML/CSS for the grid layout.
3. **Phase 3: Event Plumbing** - Connect the existing MQTT subscriber to the Pyloid bridge.
4. **Phase 4: Component Porting** - Re-implement `AgentCard` logic in `app.js`.
5. **Phase 5: Cleanup** - Remove `tkinter` and `pyperclip` (if replaced by Pyloid/Qt clipboard features) dependencies.

## 6. Testing Strategy
- **Unit Tests:** Verify the `Bridge` methods (e.g., clipboard interaction) in isolation.
- **Integration Tests:** Use simulated MQTT messages to ensure the `agent-update` signal correctly propagates to the JS layer.
- **Visual Verification:** Ensure the grid is responsive and cards handle long log messages without breaking layout.
