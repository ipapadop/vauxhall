// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { updateAgentHistory } from '../../../vauxhall/dashboard/ui/js/state.js';
import { closeHistoryModal, createCard, openHistoryModal } from '../../../vauxhall/dashboard/ui/js/ui.js';

const KEY = '["Codex","/home/user/project","session-1"]';
const VIEWPORT_HEIGHT = 200;
const CONTENT_HEIGHT = 1000;

/**
 * Builds the modal page. Called from each test rather than a shared hook, so a
 * hook in another test file cannot replace the document mid-test.
 * @returns {Document} The modal document.
 */
function setupPage() {
    const { document, window } = parseHTML(`
        <html><body>
            <div id="history-modal"></div>
            <div id="modal-agent-name"></div>
            <input id="modal-search" value="">
            <select id="modal-state-filter">
                <option value="ALL" selected>All</option>
                <option value="Acting">Acting</option>
                <option value="Error">Error</option>
                <option value="Waiting">Waiting</option>
            </select>
            <div id="modal-history-body"></div>
        </body></html>
    `);
    globalThis.document = document;
    globalThis.window = window;

    // linkedom does not lay out elements, so the modal's scroll geometry is
    // supplied here to exercise the follow-the-tail behavior.
    const body = document.getElementById('modal-history-body');
    body.scrollTop = 0;
    Object.defineProperty(body, 'scrollHeight', { value: CONTENT_HEIGHT, configurable: true });
    Object.defineProperty(body, 'clientHeight', { value: VIEWPORT_HEIGHT, configurable: true });
    return document;
}

/**
 * Builds a card carrying the given events as history, oldest first.
 * @param {object[]} events - Telemetry events to record, oldest first.
 * @returns {HTMLElement} The card.
 */
function cardWithHistory(events) {
    const card = createCard(
        { agent: 'Codex', workspace: '/home/user/project', session_id: 'session-1' },
        null,
        () => {},
    );
    events.forEach((event) => updateAgentHistory(card, event));
    return card;
}

/**
 * Chooses a state in the modal's filter, the way clicking an option would.
 * @param {Document} document - The modal document.
 * @param {string} value - The value of the option to select.
 */
function selectState(document, value) {
    const { options } = document.getElementById('modal-state-filter');
    // Deselecting an option after selecting another clears the selection in
    // linkedom, so the choice is made only once nothing else is selected.
    for (const option of options) option.selected = false;
    for (const option of options) {
        if (option.value === value) option.selected = true;
    }
}

/**
 * Returns the rendered history entries, top to bottom.
 * @param {Document} document - The modal document.
 * @returns {Array<{state: string, details: string}>} The rendered entries.
 */
function rendered(document) {
    return [...document.querySelectorAll('.history-item')].map((item) => ({
        state: item.querySelector('.history-state').textContent,
        details: item.querySelector('.history-details').textContent,
    }));
}

test('history keeps the twenty newest events, newest first', () => {
    setupPage();
    const events = Array.from({ length: 25 }, (_, index) => ({
        state: 'Acting',
        details: { tool: `tool-${index}` },
    }));

    const card = cardWithHistory(events);

    assert.equal(card.history.length, 20);
    assert.equal(card.history[0].details.tool, 'tool-24');
    assert.equal(card.history.at(-1).details.tool, 'tool-5');
});

test('history copies the details so later mutation cannot change the record', () => {
    setupPage();
    const details = { tool: 'shell' };
    const card = cardWithHistory([{ state: 'Acting', details }]);

    details.tool = 'rewritten';

    assert.equal(card.history[0].details.tool, 'shell');
});

test('an event without details records an empty object', () => {
    setupPage();

    const card = cardWithHistory([{ state: 'Idle' }]);

    assert.deepEqual(card.history[0].details, {});
});

test('opening the modal shows it and renders the history oldest first', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Thinking', details: { prompt: 'first' } },
        { state: 'Acting', details: { tool: 'shell' } },
        { state: 'Error', details: { error: 'boom' } },
    ]);

    openHistoryModal(KEY, { [KEY]: card });

    assert.equal(document.getElementById('history-modal').style.display, 'block');
    assert.equal(document.getElementById('modal-agent-name').textContent, `History: ${KEY}`);
    assert.deepEqual(rendered(document), [
        { state: 'Thinking', details: 'Prompt: first' },
        { state: 'Acting', details: 'Running: shell' },
        { state: 'Error', details: 'Error: boom' },
    ]);
});

test('opening the modal scrolls to the newest event', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);

    openHistoryModal(KEY, { [KEY]: card });

    assert.equal(document.getElementById('modal-history-body').scrollTop, CONTENT_HEIGHT);
});

test('closing the modal hides it', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);
    openHistoryModal(KEY, { [KEY]: card });

    closeHistoryModal();

    assert.equal(document.getElementById('history-modal').style.display, 'none');
});

test('the search box narrows the history to matching details', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Acting', details: { tool: 'shell', cmd: 'npm test' } },
        { state: 'Acting', details: { tool: 'read_file' } },
        { state: 'Error', details: { error: 'shell exited 1' } },
    ]);
    document.getElementById('modal-search').value = 'shell';

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document).map((item) => item.details), [
        'Running: shell npm test',
        'Error: shell exited 1',
    ]);
});

test('the search box ignores case', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'Shell' } }]);
    document.getElementById('modal-search').value = 'SHELL';

    openHistoryModal(KEY, { [KEY]: card });

    assert.equal(rendered(document).length, 1);
});

test('a search matching nothing renders an empty history', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);
    document.getElementById('modal-search').value = 'no-such-tool';

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document), []);
});

test('the state filter keeps only events in that state', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Acting', details: { tool: 'shell' } },
        { state: 'Error', details: { error: 'boom' } },
        { state: 'Acting', details: { tool: 'grep' } },
    ]);
    selectState(document, 'Error');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document), [{ state: 'Error', details: 'Error: boom' }]);
});

test('the waiting filter also matches events waiting for input', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Waiting for Input', details: { prompt: 'approve?' } },
        { state: 'Waiting', details: { prompt: 'continue?' } },
        { state: 'Acting', details: { tool: 'shell' } },
    ]);
    selectState(document, 'Waiting');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document).map((item) => item.state), ['Waiting for Input', 'Waiting']);
});

test('the all filter keeps every event', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Acting', details: { tool: 'shell' } },
        { state: 'Idle', details: { status: 'Ready' } },
    ]);
    selectState(document, 'ALL');

    openHistoryModal(KEY, { [KEY]: card });

    assert.equal(rendered(document).length, 2);
});

test('the search box and the state filter apply together', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Acting', details: { tool: 'shell' } },
        { state: 'Acting', details: { tool: 'grep' } },
        { state: 'Error', details: { error: 'shell exited 1' } },
    ]);
    document.getElementById('modal-search').value = 'shell';
    selectState(document, 'Acting');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document), [{ state: 'Acting', details: 'Running: shell' }]);
});

test('a live update re-renders without retitling or reopening the modal', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);
    const agents = { [KEY]: card };
    openHistoryModal(KEY, agents);
    document.getElementById('modal-agent-name').textContent = 'untouched';
    document.getElementById('history-modal').style.display = 'none';

    updateAgentHistory(card, { state: 'Error', details: { error: 'boom' } });
    openHistoryModal(KEY, agents, true);

    assert.equal(document.getElementById('modal-agent-name').textContent, 'untouched');
    assert.equal(document.getElementById('history-modal').style.display, 'none');
    assert.deepEqual(rendered(document).map((item) => item.state), ['Acting', 'Error']);
});

test('a live update follows new events while the view sits at the bottom', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);
    const body = document.getElementById('modal-history-body');
    body.scrollTop = CONTENT_HEIGHT - VIEWPORT_HEIGHT;

    openHistoryModal(KEY, { [KEY]: card }, true);

    assert.equal(body.scrollTop, CONTENT_HEIGHT);
});

test('a live update keeps the scroll position when the view is scrolled back', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);
    const body = document.getElementById('modal-history-body');
    body.scrollTop = 100;

    openHistoryModal(KEY, { [KEY]: card }, true);

    assert.equal(body.scrollTop, 100);
});

test('the modal ignores a key with no card and a card with no history', () => {
    const document = setupPage();
    const body = document.getElementById('modal-history-body');
    const withoutHistory = document.createElement('div');

    openHistoryModal(KEY, {});
    openHistoryModal(KEY, { [KEY]: withoutHistory });

    assert.equal(body.children.length, 0);
    assert.equal(document.getElementById('history-modal').style.display, '');
});
