/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
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
    const pyloidIpc = window.ipc;

    if (pyloidEvent && pyloidEvent.listen) {
        pyloidEvent.listen('agent-update', callbacks.onAgentUpdate);
        pyloidEvent.listen('status-update', callbacks.onStatusUpdate);
    }

    if (pyloidIpc && pyloidIpc.DashboardIPC) {
        // Verify bridge health before signaling ready
        pyloidIpc.DashboardIPC.ping().then(alive => {
            if (alive) {
                pyloidIpc.DashboardIPC.set_ready().then(() => {
                    if (callbacks.onReady) callbacks.onReady();
                });
            }
        }).catch(err => {
            console.error("IPC Health Check Failed:", err);
            if (callbacks.onError) callbacks.onError("IPC Connection Failed");
        });
    } else {
        if (callbacks.onError) callbacks.onError("DashboardIPC not found");
    }
}
