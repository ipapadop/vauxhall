/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file ipc.js
 * @description Manages communication with the Python backend.
 */

/**
 * Initializes the IPC connection and sets up listeners.
 * @param {IPCCallbacks} callbacks - An object containing callback functions for various events.
 */
export function initIPC(callbacks) {
    const pyloidEvent = window.pyloid.event || window.pyloid.EventAPI;
    const dashboardIpc = window.ipc?.DashboardIPC;

    if (pyloidEvent?.listen) {
        pyloidEvent.listen('agent-update', callbacks.onAgentUpdate);
        pyloidEvent.listen('status-update', callbacks.onStatusUpdate);
    }

    if (!dashboardIpc) {
        callbacks.onError?.("DashboardIPC not found");
        return;
    }

    // Verify bridge health before signaling ready
    dashboardIpc.ping().then(alive => {
        if (alive) dashboardIpc.set_ready().then(() => callbacks.onReady?.());
    }).catch(err => {
        console.error("IPC Health Check Failed:", err);
        callbacks.onError?.("IPC Connection Failed");
    });
}
