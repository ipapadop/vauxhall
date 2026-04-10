/**
 * @file ipc.js
 * @description Manages communication with the Python backend.
 */

/**
 * Initializes the IPC connection and sets up listeners.
 * @param {Object} callbacks - An object containing callback functions for various events.
 */
export function initIPC(callbacks) {
    const pyloidEvent = window.pyloid.event || window.pyloid.EventAPI;
    const pyloidIpc = window.ipc;

    if (pyloidEvent && pyloidEvent.listen) {
        pyloidEvent.listen('agent-update', callbacks.onAgentUpdate);
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

/**
 * Shows a desktop notification via the backend.
 * @param {string} title - The notification title.
 * @param {string} message - The notification message body.
 * @returns {Promise<boolean>}
 */
export function notify(title, message) {
    if (window.ipc && window.ipc.DashboardIPC) {
        return window.ipc.DashboardIPC.notify(title, message);
    }
    return Promise.resolve(false);
}
