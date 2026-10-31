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
 * Saves a new agent denylist through the settings bridge, alongside any other
 * pending field changes so they are not discarded by the same save.
 * @param {object} ipc - The DashboardIPC bridge.
 * @param {string[]} next - The denylist to save.
 * @param {object} [changes] - Other pending changes, grouped by section (as returned by collectChanges).
 * @returns {Promise<{ok: boolean, error?: string}>} The save outcome.
 */
export async function saveDenylist(ipc, next, changes = {}) {
    return JSON.parse(await ipc.save_settings(JSON.stringify({
        changes: { ...changes, dashboard: { ...changes.dashboard, agent_denylist: next } },
        update_hooks: false,
    })));
}

/**
 * Adds an agent to the saved denylist, logging why when it can't.
 * @param {object} ipc - The DashboardIPC bridge.
 * @param {string} agentName - The agent to add.
 */
export async function addToDenylist(ipc, agentName) {
    try {
        const descriptor = JSON.parse(await ipc.get_settings());
        if (descriptor.error) {
            console.error('Failed to update agent denylist:', descriptor.error);
            return;
        }
        if (descriptor.agent_denylist_editable === false) {
            console.error('Failed to add agent to denylist: a configuration file in the current directory takes precedence.');
            return;
        }
        const denylist = descriptor.agent_denylist ?? [];
        if (denylist.includes(agentName)) return;
        const result = await saveDenylist(ipc, [...denylist, agentName]);
        if (!result.ok) console.error('Failed to add agent to denylist:', result.error);
    } catch (err) {
        console.error('Failed to update agent denylist:', err);
    }
}
