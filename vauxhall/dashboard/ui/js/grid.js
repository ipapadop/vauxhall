/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file grid.js
 * @description Filters, sorts, and summarizes the agent grid, and marks stale cards.
 */

import { element } from './dom.js';
import { formatTokens, isAttentionCard, tokensOf } from './card.js';
import { prefersReducedMotion } from './motion.js';

const STATUS_ORDER = { 'Error': 0, 'Input Required': 1, 'Waiting for Input': 1, 'Acting': 2, 'Thinking': 2, 'Idle': 3, 'STALE': 4 };


/**
 * Returns the text of a card's first matching element, or an empty string.
 * @param {HTMLElement} card - The agent card.
 * @param {string} selector - Selector for the element to read.
 * @returns {string} The element's text.
 */
const textOf = (card, selector) => card.querySelector(selector)?.textContent || '';

const CARD_COMPARATORS = {
    name: (a, b) => textOf(a, '.agent-name').localeCompare(textOf(b, '.agent-name')),
    recent: (a, b) => parseInt(b.dataset.lastSeen || '0') - parseInt(a.dataset.lastSeen || '0'),
    status: (a, b) => (STATUS_ORDER[textOf(a, '.status-badge')] ?? 9) - (STATUS_ORDER[textOf(b, '.status-badge')] ?? 9),
    tokens: (a, b) => tokensOf(b) - tokensOf(a),
};

/**
 * Filters the agent grid.
 * @param {string} query - The search query.
 * @param {object} agents - The agents state object.
 */
export function filterGrid(query, agents) {
    Object.values(agents).forEach(card => {
        const nameElement = card.querySelector('.agent-name');
        const workspaceElement = card.querySelector('.agent-workspace');
        if (!nameElement || !workspaceElement) return;

        const name = nameElement.textContent?.toLowerCase() || '';
        const workspace = workspaceElement.textContent?.toLowerCase() || '';
        const matches = name.includes(query) || workspace.includes(query);
        card.style.display = matches && card.dataset.hidden !== 'true' ? 'flex' : 'none';
    });
}

/**
 * Sorts the agent grid.
 * @param {string} criteria - The sort criteria.
 * @param {HTMLElement} grid - The agent grid element.
 * @param {boolean} [attentionFirst] - Whether to rank cards needing attention
 *   (Error or Waiting) before the rest, regardless of `criteria`.
 */
export function sortGrid(criteria, grid, attentionFirst = false) {
    const cardsArray = Array.from(grid.children);

    // FIRST: Record positions
    const firstPositions = cardsArray.map(card => {
        const rect = card.getBoundingClientRect();
        return { card, top: rect.top, left: rect.left };
    });

    // LAST: Re-sort DOM
    const compare = Object.hasOwn(CARD_COMPARATORS, criteria) ? CARD_COMPARATORS[criteria] : () => 0;
    const rank = attentionFirst
        ? (a, b) => (Number(isAttentionCard(b)) - Number(isAttentionCard(a))) || compare(a, b)
        : compare;
    cardsArray.sort(rank).forEach(card => grid.appendChild(card));

    if (prefersReducedMotion()) return;

    // INVERT & PLAY
    requestAnimationFrame(() => {
        firstPositions.forEach(({ card, top, left }) => {
            const rect = card.getBoundingClientRect();
            const deltaX = left - rect.left;
            const deltaY = top - rect.top;
            if (deltaX === 0 && deltaY === 0) return;

            card.style.transition = 'none';
            card.style.transform = `translate(${deltaX}px, ${deltaY}px)`;

            requestAnimationFrame(() => {
                // Use CSS variable for consistent speed
                card.style.transition = 'transform var(--transition-speed) ease-out';
                card.style.transform = '';

                // Clear styles after transition to restore CSS hover etc.
                card.addEventListener('transitionend', () => {
                    card.style.transition = '';
                    card.style.transform = '';
                }, { once: true });
            });
        });
    });
}

/**
 * Tallies the fleet across every tracked card.
 * @param {object} agents - The agents state object.
 * @returns {{total: number, attention: number, stale: number, tokens: number}} The fleet totals.
 */
export function summarizeAgents(agents) {
    let total = 0, attention = 0, stale = 0, tokens = 0;
    for (const card of Object.values(agents)) {
        total++;
        if (card.classList.contains('stale')) stale++;
        if (isAttentionCard(card)) attention++;
        tokens += tokensOf(card);
    }
    return { total, attention, stale, tokens };
}

/**
 * Renders the fleet summary badges (total, needs attention, stale, tokens).
 * @param {HTMLElement | null} container - The summary bar element.
 * @param {object} agents - The agents state object.
 */
export function renderSummary(container, agents) {
    if (!container) return;
    const { total, attention, stale, tokens } = summarizeAgents(agents);

    const badge = (className, text, title) => {
        const span = element('span', className, text);
        span.title = title;
        return span;
    };

    container.replaceChildren(
        badge('summary-badge', `${total} agent${total === 1 ? '' : 's'}`, 'Total agent cards'),
        badge(`summary-badge${attention > 0 ? ' summary-attention' : ''}`, `${attention} need${attention === 1 ? 's' : ''} attention`, 'Cards in Error or Waiting state'),
        badge('summary-badge', `${stale} stale`, 'Cards past the stale threshold'),
        badge('summary-badge', `${formatTokens(tokens)} tokens`, 'Combined tokens across active operations'),
    );
}

/**
 * Checks for stale agents and updates the last seen timer.
 * @param {object} agents - The agents state object.
 * @param {number} staleThresholdMs - The staleness threshold in milliseconds.
 */
export function checkStaleness(agents, staleThresholdMs = 120000) {
    const now = Date.now();

    Object.values(agents).forEach(card => {
        const diff = now - parseInt(card.dataset.lastSeen || '0');

        const timer = card.querySelector('.last-seen-timer');
        if (timer) {
            timer.textContent = diff < 60000 ? 'just now' : `${Math.floor(diff / 60000)}m ago`;
        }

        const isStale = diff > staleThresholdMs;
        card.classList.toggle('stale', isStale);
        const statusBadge = card.querySelector('.status-badge');
        if (statusBadge) statusBadge.textContent = isStale ? 'STALE' : (card.dataset.state || 'Idle');
    });
}
