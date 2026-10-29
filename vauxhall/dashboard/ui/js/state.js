/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file state.js
 * @description Manages the global state of the dashboard, including agent tracking and history.
 */

export const agents = {}; // JSON [agent, session_id] -> DOM element

/**
 * Builds the key that identifies one agent card.
 *
 * The workspace is left out: it is the agent's current directory, which can
 * change during a session, and the card follows it.
 * @param {object} data - Telemetry data naming the agent and session.
 * @returns {string} The card key.
 */
export function agentKey(data) {
    return JSON.stringify([
        String(data.agent ?? ''),
        String(data.session_id ?? ''),
    ]);
}

/**
 * Reads the identity a card was built from.
 * @param {HTMLElement} card - The agent card element.
 * @returns {{agent: string, workspace: string, session_id: string}} The identity.
 */
export function cardIdentity(card) {
    return {
        agent: card.querySelector('.agent-name')?.textContent || '',
        workspace: card.querySelector('.agent-workspace')?.textContent || '',
        session_id: card.querySelector('.agent-session')?.title || '',
    };
}

/**
 * Snapshots each card's identity and last known state for persistence.
 * Never includes prompt, message, command, error, token, or history content.
 * @param {object} agents - The agents state object.
 * @returns {Array<object>} One entry per card: agent, workspace, session_id,
 *   state, last_seen, and env when known.
 */
export function snapshotAgents(agents) {
    return Object.values(agents).map(card => {
        const entry = {
            ...cardIdentity(card),
            state: card.dataset.state || 'Idle',
            last_seen: Number(card.dataset.lastSeen || 0),
        };
        const env = card.querySelector('.env-badge')?.textContent;
        if (env) entry.env = env;
        return entry;
    });
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
 * @param {number} [at] - Arrival time in milliseconds since the epoch.
 */
export function updateAgentHistory(card, data, at = Date.now()) {
    card.history.unshift({
        time: new Date(at).toLocaleTimeString(),
        at,
        state: data.state,
        details: structuredClone(data.details || {}) // deep copy
    });

    if (card.history.length > 20) {
        card.history.pop();
    }
}

/**
 * Returns how long each history entry lasted: until the next entry arrived,
 * or until `now` for the newest.
 * @param {Array<{at: number}>} history - History entries, newest first.
 * @param {number} [now] - The current time in milliseconds since the epoch.
 * @returns {number[]} Milliseconds per entry.
 */
export function historyDurations(history, now = Date.now()) {
    return history.map((entry, index) => Math.max(0, (index === 0 ? now : history[index - 1].at) - entry.at));
}

/**
 * Returns whether an event ends a session the user cleared, as with `/clear`.
 * @param {object} data - The telemetry data.
 * @returns {boolean} Whether the event reports a session ended by clearing.
 */
export function isClearedSession(data) {
    return data.state === 'Idle' && data.details?.end_reason === 'clear';
}

/**
 * Returns whether an event is a late copy of the message that ended the turn.
 *
 * Claude Code runs its message and stop hooks at the same time, so the
 * final message's Thinking event can arrive after the Idle event that
 * already carries it.
 * @param {HTMLElement} card - The agent card element.
 * @param {object} data - The telemetry data.
 * @returns {boolean} Whether the event only repeats the idle card's message.
 */
export function isLateFinalMessage(card, data) {
    const [latest] = card.history;
    const details = data.details || {};
    return latest?.state === 'Idle'
        && data.state === 'Thinking'
        && Object.keys(details).length === 1
        && typeof details.message === 'string'
        && details.message === latest.details.message;
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

/**
 * Returns whether a card is hidden, snoozed from the "Hide until next event" menu action.
 * @param {HTMLElement} card - The agent card element.
 * @returns {boolean} Whether the card is hidden.
 */
export function isHidden(card) {
    return card.dataset.hidden === 'true';
}

/**
 * Hides a card until its agent reports a new event, or shows it again.
 * @param {HTMLElement} card - The agent card element.
 * @param {boolean} hidden - Whether the card should be hidden.
 */
export function setHidden(card, hidden) {
    if (hidden) {
        card.dataset.hidden = 'true';
        card.style.display = 'none';
    } else {
        delete card.dataset.hidden;
        card.style.display = '';
    }
}
