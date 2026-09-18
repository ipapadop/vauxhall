/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file state.js
 * @description Manages the global state of the dashboard, including agent tracking and history.
 */

export const agents = {}; // JSON [agent, workspace, session_id] -> DOM element

/**
 * Builds the key that identifies one agent card.
 * @param {object} data - Telemetry data naming the agent, workspace, and session.
 * @returns {string} The card key.
 */
export function agentKey(data) {
    return JSON.stringify([
        String(data.agent ?? ''),
        String(data.workspace ?? ''),
        String(data.session_id ?? ''),
    ]);
}

/**
 * Removes the least recently seen cards until at most `maxAgents` remain.
 * @param {number} maxAgents - Maximum number of cards to retain.
 * @returns {string[]} The evicted card keys, oldest first.
 */
export function evictAgents(maxAgents) {
    const entries = Object.entries(agents);
    const surplus = entries.length - Math.max(maxAgents, 0);
    if (surplus <= 0) return [];

    entries.sort(([leftKey, left], [rightKey, right]) => {
        const age = Number(left.dataset.lastSeen || 0) - Number(right.dataset.lastSeen || 0);
        return age || leftKey.localeCompare(rightKey);
    });

    return entries.slice(0, surplus).map(([key, card]) => {
        card.remove();
        delete agents[key];
        return key;
    });
}

/**
 * Removes the least recently seen cards so a new card fits within capacity.
 * @param {number} maxAgents - Maximum number of cards to retain.
 * @returns {string[]} The evicted card keys, oldest first.
 */
export function ensureAgentCapacity(maxAgents) {
    return evictAgents(maxAgents - 1);
}

/**
 * Prepends an event to the card's history, keeping the newest 20 entries.
 * @param {HTMLElement} card - The agent card element.
 * @param {object} data - The telemetry data.
 */
export function updateAgentHistory(card, data) {
    card.history ??= [];

    card.history.unshift({
        time: new Date().toLocaleTimeString(),
        state: data.state,
        details: structuredClone(data.details || {}) // deep copy
    });
    
    if (card.history.length > 20) {
        card.history.pop();
    }
}

/**
 * Tracks the last seen time for an agent.
 * @param {HTMLElement} card - The agent card element.
 */
export function updateLastSeen(card) {
    card.dataset.lastSeen = Date.now().toString();
    card.classList.remove('stale');
}

/**
 * Clears all agents from the state.
 */
export function clearAgents() {
    for (const key in agents) {
        delete agents[key];
    }
}

/**
 * Removes a specific agent from the state.
 * @param {string} key - The agent key.
 */
export function removeAgent(key) {
    delete agents[key];
}
