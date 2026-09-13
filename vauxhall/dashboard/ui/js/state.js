/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file state.js
 * @description Manages the global state of the dashboard, including agent tracking and history.
 */

export const agents = {}; // JSON [agent, workspace, session_id] -> DOM element

export function agentKey(data) {
    return JSON.stringify([
        String(data.agent ?? ''),
        String(data.workspace ?? ''),
        String(data.session_id ?? ''),
    ]);
}

/**
 * Removes the least recently seen card when a new card would exceed capacity.
 * @param {number} maxAgents - Maximum number of cards to retain.
 * @returns {string | null} The evicted card key, if any.
 */
export function ensureAgentCapacity(maxAgents) {
    const entries = Object.entries(agents);
    if (entries.length < maxAgents) return null;

    entries.sort(([leftKey, left], [rightKey, right]) => {
        const age = Number(left.dataset.lastSeen || 0) - Number(right.dataset.lastSeen || 0);
        return age || leftKey.localeCompare(rightKey);
    });

    const [key, card] = entries[0];
    card.remove();
    delete agents[key];
    return key;
}

/**
 * Ensures an agent's history buffer is initialized and updated.
 * @param {HTMLElement} card - The agent card element.
 * @param {object} data - The telemetry data.
 */
export function updateAgentHistory(card, data) {
    if (!card.history) card.history = [];
    
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
