/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file prompt.js
 * @description Sending prompts to agent sessions and showing how delivery went.
 */

import { cardIdentity } from './state.js';

export const ACK_TIMEOUT_MS = 10000;

const FAILURE_REASONS = {
    'pane-unavailable': 'its tmux pane is no longer available',
    'delivery-failed': 'tmux could not type it in',
};
const MAX_REMEMBERED = 20;

/** Prompts waiting for a relay: message id -> the card and its timeout. */
const pending = new Map();
/** Timed-out prompts whose late acknowledgment can still be shown: message id -> card. */
const expired = new Map();
/** Acknowledgments that beat the bridge's reply carrying their message id. */
const unmatched = new Map();

/**
 * Adds an entry to a map, dropping the oldest once it holds more than MAX_REMEMBERED.
 * @param {Map<string, any>} map - The map to add to.
 * @param {string} key - The message id.
 * @param {any} value - The value to keep.
 */
function remember(map, key, value) {
    map.set(key, value);
    if (map.size > MAX_REMEMBERED) map.delete(map.keys().next().value);
}

/**
 * Shows the delivery state of a prompt on a card's live region, unless a newer
 * prompt from the same card has replaced it, so an older prompt's timeout or
 * late acknowledgment never overwrites the latest one's outcome.
 * @param {HTMLElement} card - The agent card.
 * @param {string} id - The message id of the prompt the state is about.
 * @param {string} text - The state to show.
 */
function setCardStatus(card, id, text) {
    if (card.latestPromptId !== id) return;
    const element = card.querySelector('.prompt-status');
    if (element) element.textContent = text;
}

/**
 * Describes an acknowledgment for the card's status line.
 * @param {{status: string, reason?: string}} ack - The relay's acknowledgment.
 * @returns {string} The text to show.
 */
function describeAck(ack) {
    if (ack.status === 'delivered') return 'Prompt delivered';
    return `Prompt not delivered: ${FAILURE_REASONS[ack.reason] ?? 'unknown error'}`;
}

/**
 * Sends a prompt to the session a card represents and starts waiting for the relay.
 * @param {any} dashboardIpc - The DashboardIPC bridge.
 * @param {HTMLElement} card - The agent card the prompt is for.
 * @param {string} text - The prompt.
 * @returns {Promise<{ok: boolean, error?: string}>} Whether it was published, or why not.
 */
export async function sendPrompt(dashboardIpc, card, text) {
    const { agent, session_id } = cardIdentity(card);
    const request = { agent, session_id, text };
    let result;
    try {
        result = JSON.parse(await dashboardIpc.send_prompt(JSON.stringify(request)));
    } catch (err) {
        console.error('Failed to send prompt:', err);
        return { ok: false, error: 'The prompt could not be sent' };
    }
    if (!result.ok) return { ok: false, error: result.error || 'The prompt could not be sent' };

    card.latestPromptId = result.id;
    const early = unmatched.get(result.id);
    if (early) {
        unmatched.delete(result.id);
        setCardStatus(card, result.id, describeAck(early));
        return { ok: true };
    }

    setCardStatus(card, result.id, 'Prompt sent, waiting for the relay…');
    const timer = setTimeout(() => {
        pending.delete(result.id);
        remember(expired, result.id, card);
        setCardStatus(card, result.id, 'No relay acknowledged the prompt');
    }, ACK_TIMEOUT_MS);
    pending.set(result.id, { card, timer });
    return { ok: true };
}

/**
 * Applies a relay's acknowledgment to the card that sent the prompt.
 * @param {{id: string, status: string, reason?: string}} ack - The acknowledgment.
 */
export function handleAck(ack) {
    if (!ack || typeof ack.id !== 'string') return;
    const entry = pending.get(ack.id);
    if (entry) {
        clearTimeout(entry.timer);
        pending.delete(ack.id);
        setCardStatus(entry.card, ack.id, describeAck(ack));
        return;
    }
    const card = expired.get(ack.id);
    if (card) {
        expired.delete(ack.id);
        setCardStatus(card, ack.id, describeAck(ack));
        return;
    }
    remember(unmatched, ack.id, ack);
}
