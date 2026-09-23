/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file denylist.js
 * @description Shared helper for saving the dashboard's agent denylist, used
 * by both the card menu and the settings dialog.
 */

/**
 * Saves a new agent denylist through the settings bridge.
 * @param {object} ipc - The DashboardIPC bridge.
 * @param {string[]} next - The denylist to save.
 * @returns {Promise<{ok: boolean, error?: string}>} The save outcome.
 */
export async function saveDenylist(ipc, next) {
    return JSON.parse(await ipc.save_settings(JSON.stringify({
        changes: { dashboard: { agent_denylist: next } },
        update_hooks: false,
    })));
}
