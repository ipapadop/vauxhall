// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { ACK_TIMEOUT_MS, handleAck, sendPrompt, showRejected } from '../../../vauxhall/dashboard/ui/js/prompt.js';
import { createCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

const IDENTITY = { agent: 'Codex', workspace: '/home/user/project', session_id: 'session-1' };

/**
 * Builds a card on the page of a fresh document.
 * @returns {HTMLElement} The card.
 */
function makeCard() {
    const { document, window } = parseHTML('<html><body></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    const card = createCard({ ...IDENTITY }, {}, () => {});
    document.body.append(card);
    return card;
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
    handleAck({ id: 'a5', status: 'delivered' });
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

test('acknowledgments of replaced prompts do not push out an early one', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    for (let index = 0; index < 25; index++) {
        await sendPrompt(bridge({ ok: true, id: `old-${index}` }).ipc, card, 'hello');
    }
    handleAck({ id: 'next', status: 'delivered' });
    for (let index = 0; index < 24; index++) handleAck({ id: `old-${index}`, status: 'delivered' });

    await sendPrompt(bridge({ ok: true, id: 'next' }).ipc, card, 'hello');

    assert.equal(status(card), 'Prompt delivered');
});

test('malformed acknowledgments leave a waiting prompt waiting', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'a9' }).ipc, card, 'hello');

    handleAck(null);
    handleAck({ status: 'delivered' });
    handleAck({ id: 5, status: 'delivered' });

    assert.equal(status(card), 'Prompt sent, waiting for the relay…');
    handleAck({ id: 'a9', status: 'delivered' });
});

test('a rejected prompt returns the error and leaves the card alone', async () => {
    const card = makeCard();

    const result = await sendPrompt(bridge({ ok: false, error: 'Prompt must not be empty' }).ipc, card, '');

    assert.deepEqual(result, { ok: false, error: 'Prompt must not be empty' });
    assert.equal(status(card), '');
});

test('a rejection shown on the card says the prompt was not sent and why', () => {
    const card = makeCard();

    showRejected(card, 'Not connected to the broker');

    assert.equal(status(card), 'Prompt not sent: Not connected to the broker');
});

for (const outcome of ['acknowledgment', 'timeout']) {
    test(`an earlier prompt's ${outcome} does not replace a rejection shown on the card`, async (t) => {
        t.mock.timers.enable({ apis: ['setTimeout'] });
        const card = makeCard();
        await sendPrompt(bridge({ ok: true, id: 'a1' }).ipc, card, 'first');

        showRejected(card, 'Not connected to the broker');
        if (outcome === 'acknowledgment') handleAck({ id: 'a1', status: 'delivered' });
        else t.mock.timers.tick(ACK_TIMEOUT_MS);

        assert.equal(status(card), 'Prompt not sent: Not connected to the broker');
    });
}

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

test('an older prompt timing out does not overwrite the newer prompt outcome', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'old-1' }).ipc, card, 'first');
    t.mock.timers.tick(ACK_TIMEOUT_MS / 2);
    await sendPrompt(bridge({ ok: true, id: 'new-1' }).ipc, card, 'second');
    handleAck({ id: 'new-1', status: 'delivered' });

    t.mock.timers.tick(ACK_TIMEOUT_MS);

    assert.equal(status(card), 'Prompt delivered');
});

test('a late acknowledgment of an older prompt does not replace the newer prompt state', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'old-2' }).ipc, card, 'first');
    await sendPrompt(bridge({ ok: true, id: 'new-2' }).ipc, card, 'second');

    handleAck({ id: 'old-2', status: 'failed', reason: 'pane-unavailable' });

    assert.equal(status(card), 'Prompt sent, waiting for the relay…');
    handleAck({ id: 'new-2', status: 'delivered' });
    assert.equal(status(card), 'Prompt delivered');
});

test('an acknowledgment after the timeout replaces the timeout message', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const card = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'late-1' }).ipc, card, 'hello');
    t.mock.timers.tick(ACK_TIMEOUT_MS);
    assert.equal(status(card), 'No relay acknowledged the prompt');

    handleAck({ id: 'late-1', status: 'delivered' });

    assert.equal(status(card), 'Prompt delivered');
});

test('late acknowledgments reach every card, however many timed out', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const cards = [];
    for (let index = 0; index < 25; index++) {
        const card = makeCard();
        cards.push(card);
        await sendPrompt(bridge({ ok: true, id: `outage-${index}` }).ipc, card, 'hello');
    }
    t.mock.timers.tick(ACK_TIMEOUT_MS);

    cards.forEach((card, index) => handleAck({ id: `outage-${index}`, status: 'delivered' }));

    assert.deepEqual(cards.map(status), cards.map(() => 'Prompt delivered'));
});

test('a prompt from a card that left the page is forgotten', async (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const removed = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'gone-1' }).ipc, removed, 'hello');
    t.mock.timers.tick(ACK_TIMEOUT_MS);
    removed.remove();
    const other = makeCard();
    await sendPrompt(bridge({ ok: true, id: 'other-1' }).ipc, other, 'hello');

    handleAck({ id: 'gone-1', status: 'delivered' });

    assert.equal(status(removed), 'No relay acknowledged the prompt');
    handleAck({ id: 'other-1', status: 'delivered' });
});
