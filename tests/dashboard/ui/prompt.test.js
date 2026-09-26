// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { ACK_TIMEOUT_MS, handleAck, sendPrompt } from '../../../vauxhall/dashboard/ui/js/prompt.js';
import { createCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

const IDENTITY = { agent: 'Codex', workspace: '/home/user/project', session_id: 'session-1' };

/**
 * Builds a card in a fresh document.
 * @returns {HTMLElement} The card.
 */
function makeCard() {
    const { document, window } = parseHTML('<html><body></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    return createCard({ ...IDENTITY }, {}, () => {});
}

/**
 * Builds a bridge whose send_prompt answers with a result and records requests.
 * @param {object | Error} result - The result to return, or an error to throw.
 * @returns {{ipc: object, requests: object[]}} The bridge and the requests it saw.
 */
function bridge(result) {
    const requests = [];
    const ipc = {
        send_prompt: async (payload) => {
            requests.push(JSON.parse(payload));
            if (result instanceof Error) throw result;
            return JSON.stringify(result);
        },
    };
    return { ipc, requests };
}

const status = (card) => card.querySelector('.prompt-status').textContent;

test('sending posts the card identity and shows that it awaits the relay', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    const { ipc, requests } = bridge({ ok: true, id: 'a1' });

    const result = await sendPrompt(ipc, card, 'hello');

    assert.deepEqual(result, { ok: true });
    assert.deepEqual(requests, [{ agent: 'Codex', session_id: 'session-1', text: 'hello' }]);
    assert.equal(status(card), 'Prompt sent, waiting for the relay…');
    handleAck({ id: 'a1', status: 'delivered' });
});

test('a delivered acknowledgment is shown and stops the timeout', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'a2' }).ipc, card, 'hello');

    handleAck({ id: 'a2', status: 'delivered' });
    t.mock.timers.tick(ACK_TIMEOUT_MS);

    assert.equal(status(card), 'Prompt delivered');
});

test('a failed acknowledgment names why', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'a3' }).ipc, card, 'hello');

    handleAck({ id: 'a3', status: 'failed', reason: 'pane-unavailable' });

    assert.equal(status(card), 'Prompt not delivered: its tmux pane is no longer available');
});

test('a failed acknowledgment with an unknown reason still reports failure', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'a4' }).ipc, card, 'hello');

    handleAck({ id: 'a4', status: 'failed', reason: 'surprise' });

    assert.equal(status(card), 'Prompt not delivered: unknown error');
});

test('no acknowledgment within the timeout is reported', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'a5' }).ipc, card, 'hello');

    t.mock.timers.tick(ACK_TIMEOUT_MS);

    assert.equal(status(card), 'No relay acknowledged the prompt');
});

test('an acknowledgment that arrives before the bridge replies is not lost', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();

    handleAck({ id: 'a6', status: 'delivered' });
    await sendPrompt(bridge({ ok: true, id: 'a6' }).ipc, card, 'hello');
    t.mock.timers.tick(ACK_TIMEOUT_MS);

    assert.equal(status(card), 'Prompt delivered');
});

test('early acknowledgments are kept only up to a limit', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    for (let index = 0; index < 25; index++) handleAck({ id: `early-${index}`, status: 'delivered' });

    await sendPrompt(bridge({ ok: true, id: 'early-0' }).ipc, card, 'hello');

    assert.equal(status(card), 'Prompt sent, waiting for the relay…');
    handleAck({ id: 'early-0', status: 'delivered' });
});

test('acknowledgments for unknown or malformed messages change nothing', () => {
    handleAck(null);
    handleAck({ status: 'delivered' });
    handleAck({ id: 5, status: 'delivered' });
});

test('a rejected prompt returns the error and leaves the card alone', async () => {
    const card = makeCard();

    const result = await sendPrompt(bridge({ ok: false, error: 'Prompt must not be empty' }).ipc, card, '');

    assert.deepEqual(result, { ok: false, error: 'Prompt must not be empty' });
    assert.equal(status(card), '');
});

test('a rejection without an error message gets a generic one', async () => {
    const result = await sendPrompt(bridge({ ok: false }).ipc, makeCard(), 'hello');

    assert.deepEqual(result, { ok: false, error: 'The prompt could not be sent' });
});

test('a bridge failure is reported without the exception details', async (t) => {
    const errors = [];
    t.mock.method(console, 'error', (...args) => errors.push(args));

    const result = await sendPrompt(bridge(new Error('secret')).ipc, makeCard(), 'hello');

    assert.deepEqual(result, { ok: false, error: 'The prompt could not be sent' });
    assert.equal(errors.length, 1);
});
