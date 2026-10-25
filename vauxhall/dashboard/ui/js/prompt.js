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
const MAX_UNMATCHED_ACKS = 20;

/**
 * Each card's latest prompt still without an acknowledgment: message id -> the
 * card and its timeout, or a null timeout once timed out, so a late
 * acknowledgment is still shown.
 */
const prompts = new Map();
/** Acknowledgments that beat the bridge's reply carrying their message id. */
const unmatched = new Map();

/**
 * Stops tracking a prompt.
 * @param {string} id - The prompt's message id.
 */
function forget(id) {
    const entry = prompts.get(id);
    if (!entry) return;
    clearTimeout(entry.timer);
    prompts.delete(id);
}

/**
 * Stops tracking a card's previous prompt, so its timeout or late
 * acknowledgment can't overwrite the new prompt's outcome, and the prompts of
 * cards that have left the page.
 * @param {HTMLElement} card - The card about to send a prompt.
 */
function forgetReplaced(card) {
    forget(card.latestPromptId);
    for (const [id, entry] of prompts) {
        if (!entry.card.isConnected) forget(id);
    }
}

/**
 * Shows the delivery state of a card's latest prompt on its live region.
 * @param {HTMLElement} card - The agent card.
 * @param {string} text - The state to show.
 */
function setCardStatus(card, text) {
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

    forgetReplaced(card);
    card.latestPromptId = result.id;
    const early = unmatched.get(result.id);
    if (early) {
        unmatched.delete(result.id);
        setCardStatus(card, describeAck(early));
        return { ok: true };
    }

    setCardStatus(card, 'Prompt sent, waiting for the relay…');
    const entry = {
        card,
        timer: setTimeout(() => {
            entry.timer = null;
            setCardStatus(card, 'No relay acknowledged the prompt');
        }, ACK_TIMEOUT_MS),
    };
    prompts.set(result.id, entry);
    return { ok: true };
}

/**
 * Shows on a card that its prompt was rejected, for a rejection whose dialog
 * has closed or moved to another card. The rejection becomes the card's
 * latest outcome, so an earlier prompt can't overwrite it.
 * @param {HTMLElement} card - The agent card the prompt was for.
 * @param {string} error - Why the prompt was not sent.
 */
export function showRejected(card, error) {
    forgetReplaced(card);
    setCardStatus(card, `Prompt not sent: ${error}`);
}

/**
 * Applies a relay's acknowledgment to the card that sent the prompt.
 * @param {{id: string, status: string, reason?: string}} ack - The acknowledgment.
 */
export function handleAck(ack) {
    if (!ack || typeof ack.id !== 'string') return;
    const entry = prompts.get(ack.id);
    if (!entry) {
        unmatched.set(ack.id, ack);
        if (unmatched.size > MAX_UNMATCHED_ACKS) unmatched.delete(unmatched.keys().next().value);
        return;
    }
    forget(ack.id);
    setCardStatus(entry.card, describeAck(ack));
}
