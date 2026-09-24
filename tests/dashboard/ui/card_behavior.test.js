// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { updateLastSeen } from '../../../vauxhall/dashboard/ui/js/state.js';
import { checkStaleness, createCard, updateCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

const IDENTITY = { agent: 'Codex', workspace: '/home/user/project', session_id: 'session-1' };

/**
 * Builds a page and a card for the standard test identity. The page is built
 * from each test rather than a shared hook, so a hook in another test file
 * cannot replace the document mid-test.
 * @returns {HTMLElement} The card.
 */
function makeCard() {
    const { document, window } = parseHTML('<html><body><div id="agent-grid"></div></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    return createCard({ ...IDENTITY }, null, () => {});
}

/**
 * Returns a card's activity log lines, newest first.
 * @param {HTMLElement} card - The agent card.
 * @returns {string[]} The log line texts.
 */
function logLines(card) {
    return [...card.querySelectorAll('.log-line')].map((line) => line.textContent);
}

/**
 * Returns the card's metric badge texts, in order.
 * @param {HTMLElement} card - The agent card.
 * @returns {string[]} The badge texts.
 */
function badges(card) {
    return [...card.querySelectorAll('.metric-badge')].map((badge) => badge.textContent);
}

test('a new card starts idle with no metrics and an empty log', () => {
    const card = makeCard();

    assert.equal(card.querySelector('.status-badge').textContent, 'Idle');
    assert.equal(card.querySelector('.log-area').textContent, 'Ready...');
    assert.deepEqual(badges(card), []);
    assert.equal(card.className, 'agent-card');
});

test('each state applies its own class and replaces the previous one', () => {
    const card = makeCard();
    const classFor = (state, details = { status: state }) => {
        updateCard(card, { state, details });
        return [...card.classList].filter((name) => name !== 'agent-card');
    };

    assert.deepEqual(classFor('Error', { error: 'boom' }), ['error']);
    assert.deepEqual(classFor('Waiting for Input', { prompt: 'continue?' }), ['waiting']);
    assert.deepEqual(classFor('Input Required', { prompt: 'approve?' }), ['waiting']);
    assert.deepEqual(classFor('Waiting', { prompt: 'still?' }), ['waiting']);
    assert.deepEqual(classFor('Acting', { tool: 'shell' }), ['working']);
    assert.deepEqual(classFor('Thinking', { status: 'planning' }), ['working']);
    assert.deepEqual(classFor('Idle', { status: 'Ready' }), []);
    assert.equal(card.querySelector('.status-badge').textContent, 'Idle');
});

test('an unknown state clears the state classes and is still shown', () => {
    const card = makeCard();
    updateCard(card, { state: 'Error', details: { error: 'boom' } });

    updateCard(card, { state: 'Reticulating', details: { status: 'splines' } });

    assert.equal(card.className, 'agent-card');
    assert.equal(card.querySelector('.status-badge').textContent, 'Reticulating');
});

test('positive metrics become badges and large token counts are abbreviated', () => {
    const card = makeCard();

    updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: 1500, duration: 2.5 } });

    assert.deepEqual(badges(card), ['1.5k', '2.5s']);
    assert.equal(card.querySelector('.metric-badge.tokens').dataset.value, '1500');
});

test('token counts at or below a thousand are shown exactly', () => {
    const card = makeCard();

    updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: 1000 } });

    assert.deepEqual(badges(card), ['1000']);
    assert.equal(card.querySelector('.metric-badge.tokens').dataset.value, '1000');
});

test('metrics that are not positive numbers are ignored', () => {
    const card = makeCard();

    for (const value of [0, -5, true, '900', Number.NaN, Number.POSITIVE_INFINITY, null]) {
        updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: value, duration: value } });
        assert.deepEqual(badges(card), [], `tokens and duration of ${String(value)}`);
    }
});

test('metrics carry across a continuing operation', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: 400, duration: 3 } });

    updateCard(card, { state: 'Thinking', details: { tool: 'shell', status: 'completed' } });

    assert.deepEqual(badges(card), ['400', '3s']);
});

test('a new operation resets the metrics of the previous one', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: 400, duration: 3 } });

    updateCard(card, { state: 'Acting', details: { tool: 'grep' } });

    assert.deepEqual(badges(card), []);
});

test('a new prompt while thinking resets the metrics', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: 400, duration: 3 } });

    updateCard(card, { state: 'Thinking', details: { prompt: 'what next?' } });

    assert.deepEqual(badges(card), []);
});

test('a new operation that reports its own metrics replaces the old ones', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell', tokens: 400, duration: 3 } });

    updateCard(card, { state: 'Acting', details: { tool: 'grep', tokens: 25, duration: 1.5 } });

    assert.deepEqual(badges(card), ['25', '1.5s']);
});

test('the activity log keeps the five newest events, newest first', () => {
    const card = makeCard();

    for (const tool of ['one', 'two', 'three', 'four', 'five', 'six']) {
        updateCard(card, { state: 'Acting', details: { tool } });
    }

    const lines = logLines(card);
    assert.equal(lines.length, 5);
    assert.match(lines[0], /Running: six$/);
    assert.match(lines.at(-1), /Running: two$/);
    assert.equal(card.querySelector('.log-area').textContent.includes('Ready...'), false);
});

test('an event repeating the previous message is not logged again', () => {
    const card = makeCard();

    updateCard(card, { state: 'Acting', details: { tool: 'shell' } });
    updateCard(card, { state: 'Acting', details: { tool: 'shell' } });

    assert.equal(logLines(card).length, 1);
});

test('an event with no reportable details leaves the log untouched', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell' } });

    updateCard(card, { state: 'Idle', details: {} });

    assert.equal(logLines(card).length, 1);
    assert.equal(card.querySelector('.status-badge').textContent, 'Idle');
});

test('a card with no events yet is marked stale and reports its age', () => {
    const card = makeCard();
    card.dataset.lastSeen = String(Date.now() - 180000);

    checkStaleness({ only: card }, 120000);

    assert.equal(card.classList.contains('stale'), true);
    assert.equal(card.querySelector('.status-badge').textContent, 'STALE');
    assert.equal(card.querySelector('.last-seen-timer').textContent, '3m ago');
});

test('a card seen within the threshold stays fresh', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell' } });
    card.dataset.lastSeen = String(Date.now() - 90000);

    checkStaleness({ only: card }, 120000);

    assert.equal(card.classList.contains('stale'), false);
    assert.equal(card.querySelector('.status-badge').textContent, 'Acting');
    assert.equal(card.querySelector('.last-seen-timer').textContent, '1m ago');
});

test('a configured threshold decides when a card turns stale', () => {
    const card = makeCard();
    card.dataset.lastSeen = String(Date.now() - 45000);

    checkStaleness({ only: card }, 30000);

    assert.equal(card.classList.contains('stale'), true);
    assert.equal(card.querySelector('.last-seen-timer').textContent, 'just now');
});

test('a stale card recovers when its agent reports again', () => {
    const card = makeCard();
    card.dataset.lastSeen = String(Date.now() - 180000);
    checkStaleness({ only: card }, 120000);

    updateLastSeen(card);
    updateCard(card, { state: 'Acting', details: { tool: 'shell' } });
    checkStaleness({ only: card }, 120000);

    assert.equal(card.classList.contains('stale'), false);
    assert.equal(card.querySelector('.status-badge').textContent, 'Acting');
    assert.equal(card.querySelector('.last-seen-timer').textContent, 'just now');
});

test('moving from Idle into Waiting or Error reports it entered attention', () => {
    const card = makeCard();
    updateCard(card, { state: 'Acting', details: { tool: 'shell' } });

    const waiting = updateCard(card, { state: 'Waiting for Input', details: { prompt: 'ok?' } });
    assert.equal(waiting.enteredAttention, true);
    assert.equal(waiting.message, 'Prompt: ok?');

    const stillWaiting = updateCard(card, { state: 'Input Required', details: { prompt: 'still?' } });
    assert.equal(stillWaiting.enteredAttention, false);

    updateCard(card, { state: 'Idle', details: { status: 'Ready' } });
    const error = updateCard(card, { state: 'Error', details: { error: 'boom' } });
    assert.equal(error.enteredAttention, true);
    assert.equal(error.message, 'Error: boom');
});

test('a fresh card entering Waiting reports it entered attention', () => {
    const card = makeCard();

    const { enteredAttention } = updateCard(card, { state: 'Waiting for Input', details: { prompt: 'ok?' } });

    assert.equal(enteredAttention, true);
});

test('an event with no log message still reports whether it entered attention', () => {
    const card = makeCard();

    const { enteredAttention, message } = updateCard(card, { state: 'Error', details: {} });

    assert.equal(enteredAttention, true);
    assert.equal(message, 'Error');
});

test('a card that goes stale while waiting does not re-report attention on its next event', () => {
    const card = makeCard();
    updateCard(card, { state: 'Waiting for Input', details: { prompt: 'ok?' } });
    // checkStaleness overwrites the badge text to "STALE" but leaves the
    // 'waiting' class alone; a naive read of the badge would see "STALE" as
    // not an attention state and wrongly report re-entering attention below.
    card.querySelector('.status-badge').textContent = 'STALE';

    const { enteredAttention } = updateCard(card, { state: 'Waiting for Input', details: { prompt: 'still?' } });

    assert.equal(enteredAttention, false);
});
