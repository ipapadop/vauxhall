/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file fleet.js
 * @description Adds, updates, and removes the agent grid's cards.
 */

import { createCard, updateCard } from './card.js';
import {
    agentKey, agents, cardIdentity, clearAgents, ensureAgentCapacity, evictAgents, isHidden,
    isLateFinalMessage, isReplacedSession, removeAgent, setHidden, updateAgentHistory, updateLastSeen,
} from './state.js';

/**
 * Creates the card operations for a grid.
 * @param {HTMLElement} grid - The agent grid element.
 * @param {object} callbacks - What the cards' controls and removals do.
 * @param {Function} callbacks.openPane - Called with a card's key and the
 *   control to focus again when the card is clicked.
 * @param {Function} callbacks.openMenu - Called with a card's key and its
 *   menu button when that button is activated.
 * @param {Function} callbacks.onRemoved - Called with the keys of cards that
 *   left the grid, except through `clear`, so dialogs acting on them close.
 * @returns {object} The fleet's operations.
 */
export function createFleet(grid, { openPane, openMenu, onRemoved }) {
    const newCard = (key, data) => createCard(
        data,
        (opener) => openPane(key, opener),
        (opener) => openMenu(key, opener),
    );
    const register = (key, card) => {
        agents[key] = card;
        grid.appendChild(card);
    };
    const remove = (key) => {
        agents[key]?.remove();
        removeAgent(key);
        onRemoved([key]);
    };

    return {
        remove,

        /** Removes every card, without closing dialogs. */
        clear() {
            grid.innerHTML = '';
            clearAgents();
        },

        /** Removes the cards marked stale. */
        removeStale() {
            for (const [key, card] of Object.entries(agents)) {
                if (card.classList.contains('stale')) remove(key);
            }
        },

        /**
         * Builds card shells saved by the previous run. The newest are kept
         * before any DOM work, so a saved list over the limit builds no card
         * only to evict it; a card already on the grid is left alone.
         * @param {unknown} saved - The saved cards.
         * @param {number} maxActiveAgents - The card limit.
         */
        restore(saved, maxActiveAgents) {
            const shells = (Array.isArray(saved) ? saved : [])
                .sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0))
                .slice(0, Math.max(maxActiveAgents, 0));
            for (const shell of shells) {
                const key = agentKey(shell);
                if (agents[key]) continue;
                const card = newCard(key, shell);
                updateCard(card, shell);
                card.dataset.lastSeen = String(shell.last_seen || 0);
                register(key, card);
            }
        },

        /**
         * Applies one telemetry event to its card, creating the card if needed.
         * @param {object} data - The telemetry event.
         * @param {number} maxActiveAgents - The card limit.
         * @returns {{key: string, removed?: boolean, enteredAttention?: boolean, message?: string} | null}
         *   `null` when the event changed nothing; `removed` when it ended a
         *   replaced session's card; otherwise `updateCard`'s result.
         */
        apply(data, maxActiveAgents) {
            const key = agentKey(data);
            let card = agents[key];
            if (card && isLateFinalMessage(card, data)) return null;

            // The agent continues a cleared or resumed-away session under
            // another session ID, so its card would only linger until stale.
            if (isReplacedSession(data)) {
                if (!card) return null;
                remove(key);
                return { key, removed: true };
            }

            if (!card) {
                onRemoved(ensureAgentCapacity(maxActiveAgents));
                card = newCard(key, data);
                register(key, card);
            } else if (isHidden(card)) {
                // A hidden card reappears on its next event.
                setHidden(card, false);
            }

            updateAgentHistory(card, data);
            updateLastSeen(card);
            return { key, ...updateCard(card, data) };
        },

        /**
         * Removes the cards of denylisted agents, then evicts down to the limit,
         * so denylisted cards don't count toward it.
         * @param {string[]} denylist - Agent names to remove.
         * @param {number} maxActiveAgents - The card limit.
         */
        applySettings(denylist, maxActiveAgents) {
            const denied = new Set(denylist);
            for (const [key, card] of Object.entries(agents)) {
                if (denied.has(cardIdentity(card).agent)) remove(key);
            }
            onRemoved(evictAgents(maxActiveAgents));
        },
    };
}
