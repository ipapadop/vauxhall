/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file state.js
 * @description Manages the global state of the dashboard, including agent tracking and history.
 */

export const agents = {}; // (agent:workspace) -> DOM element

/**
 * Ensures an agent's history buffer is initialized and updated.
 * @param {HTMLElement} card - The agent card element.
 * @param {Object} data - The telemetry data.
 */
export function updateAgentHistory(card, data) {
    if (!card.history) card.history = [];
    
    card.history.unshift({
        time: new Date().toLocaleTimeString(),
        state: data.state,
        details: JSON.parse(JSON.stringify(data.details || {})) // deep copy
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
    card.dataset.lastSeen = Date.now();
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

/**
 * Updates the token history for an agent.
 * @param {HTMLElement} card - The agent card element.
 * @param {number} tokens - The current token count.
 */
export function updateTokenHistory(card, tokens) {
    if (!card.tokenHistory) card.tokenHistory = [];
    if (tokens === undefined || tokens === null) return;
    
    card.tokenHistory.push(tokens);
    
    if (card.tokenHistory.length > 20) {
        card.tokenHistory.shift();
    }
}
