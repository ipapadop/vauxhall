# Design: Dashboard Resilience, Interactivity, and Smooth Transitions

**Date:** 2026-04-15
**Status:** Approved
**Topic:** Improving MQTT resilience, adding interactive history, and implementing smooth grid transitions.

## 1. Overview
This design aims to improve the robustness and polish of the Vauxhall Dashboard. We will enhance the MQTT connection handling, add filtering capabilities to the agent history modal, and implement smooth grid animations when sorting or adding agents.

## 2. Architecture & Components

### 2.1 Backend: State-Aware MQTT Subscriber
The `DashboardSubscriber` in `vauxhall/dashboard/mqtt_client.py` will be refactored to handle connection states more explicitly.

- **Status Callback**: A new `on_status` callback will be added to the `__init__` method.
- **Connection Logic**:
    - `_on_connect`: Update the status to "Connected to Agent Fleet" on success (rc=0), or a descriptive error message on failure.
    - `_on_disconnect`: Update the status to "Disconnected. Retrying..."
- **Resilience**: Paho-MQTT's background loop (`loop_start()`) will handle automatic reconnections. The subscriber will remain thin, primarily acting as a state-to-IPC bridge.

### 2.2 Frontend: Interactive History
The history modal (`vauxhall/dashboard/ui/index.html` and `vauxhall/dashboard/ui/js/ui.js`) will gain real-time filtering.

- **UI Elements**:
    - A search input (`modal-search`) in the modal header for keyword filtering in logs.
    - A state dropdown (`modal-state-filter`) to filter events by their status (e.g., "Error", "Acting").
- **Logic**:
    - `openHistoryModal` will be updated to take the current search/filter values into account.
    - A new `renderHistory` function will isolate the DOM injection logic for re-rendering during user interaction.

### 2.3 Frontend: Smooth Grid Transitions (FLIP)
The agent grid (`vauxhall/dashboard/ui/js/ui.js`) will implement the FLIP (First, Last, Invert, Play) animation technique.

- **Process**:
    1. **First**: Record the `getBoundingClientRect()` of all agent cards before sorting.
    2. **Last**: Re-sort the DOM nodes in the grid.
    3. **Invert**: Calculate the translation offset (`oldX - newX`, `oldY - newY`) and apply a CSS `transform: translate(...)` and `transition: none` to instantly "fake" the old position.
    4. **Play**: Wait for a frame (`requestAnimationFrame`) and then clear the transform and apply a `transition: transform 0.4s ease-out`.
- **Result**: Cards slide smoothly into their new positions when the user changes sorting criteria or when the grid is refreshed.

## 3. Data Flow
1. **MQTT Event** -> `DashboardSubscriber` -> `DashboardIPC` -> `app.js` -> `ui.js` -> Card Update.
2. **Sort Change** -> `ui.js:sortGrid` -> FLIP calculation -> DOM Reorder -> Animation.
3. **Modal Filter** -> `ui.js:openHistoryModal` -> Filtered `card.history` -> DOM Update.

## 4. Testing Strategy
- **Backend**: Update `tests/test_dashboard_mqtt.py` to verify that the `on_status` callback is called correctly during connection and disconnection.
- **Frontend**: Manual verification of the history search bar and FLIP animations.
- **Integration**: Verify that `js-status` text updates appropriately when the MQTT broker is toggled.

## 5. Success Criteria
- [ ] Dashboard displays "Connected" status and updates text when the broker goes down.
- [ ] History modal can be searched and filtered by state.
- [ ] Agent cards slide smoothly to their new positions during re-sorting (no "jumps").
- [ ] All 29+ tests pass.
