// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { historyDurations, updateAgentHistory } from '../../../vauxhall/dashboard/ui/js/state.js';
import {
    closeHistoryModal, copyWorkspacePath, createCard, formatDuration, openHistoryModal,
} from '../../../vauxhall/dashboard/ui/js/ui.js';

import { selectOption } from './helpers.js';

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
            <dialog id="history-modal"><div class="modal-content"></div></dialog>
            <div id="modal-agent-name"></div>
            <div id="modal-agent-meta"></div>
            <span id="modal-copy-status">Copied!</span>
            <input id="modal-search" value="">
            <select id="modal-state-filter">
                <option value="ALL" selected>All</option>
                <option value="Acting">Acting</option>
                <option value="Error">Error</option>
                <option value="Waiting for Input">Waiting</option>
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
        () => {},
    );
    events.forEach((event) => updateAgentHistory(card, event));
    return card;
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

test('a new card starts with an empty history', () => {
    setupPage();

    assert.deepEqual(cardWithHistory([]).history, []);
});

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

    assert.ok(document.getElementById('history-modal').hasAttribute('open'));
    assert.equal(document.getElementById('modal-agent-name').textContent, 'Codex');
    assert.equal(document.getElementById('modal-agent-meta').textContent, '/home/user/project · session session-1');
    assert.equal(document.getElementById('modal-copy-status').textContent, '');
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

    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
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
    selectOption(document.getElementById('modal-state-filter'), 'Error');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document), [{ state: 'Error', details: 'Error: boom' }]);
});

test('the waiting filter matches every waiting state', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Waiting for Input', details: { prompt: 'continue?' } },
        { state: 'Input Required', details: { prompt: 'approve?' } },
        { state: 'Acting', details: { tool: 'shell' } },
    ]);
    selectOption(document.getElementById('modal-state-filter'), 'Waiting for Input');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document).map((item) => item.state), ['Waiting for Input', 'Input Required']);
});

test('the all filter keeps every event', () => {
    const document = setupPage();
    const card = cardWithHistory([
        { state: 'Acting', details: { tool: 'shell' } },
        { state: 'Idle', details: { status: 'Ready' } },
    ]);
    selectOption(document.getElementById('modal-state-filter'), 'ALL');

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
    selectOption(document.getElementById('modal-state-filter'), 'Acting');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(rendered(document), [{ state: 'Acting', details: 'Running: shell' }]);
});

test('a live update re-renders without retitling or reopening the modal', () => {
    const document = setupPage();
    const card = cardWithHistory([{ state: 'Acting', details: { tool: 'shell' } }]);
    const agents = { [KEY]: card };
    openHistoryModal(KEY, agents);
    document.getElementById('modal-agent-name').textContent = 'untouched';
    document.getElementById('history-modal').removeAttribute('open');

    updateAgentHistory(card, { state: 'Error', details: { error: 'boom' } });
    openHistoryModal(KEY, agents, true);

    assert.equal(document.getElementById('modal-agent-name').textContent, 'untouched');
    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
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
    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
});

/**
 * Builds a card whose history entries arrived at the given times, oldest first.
 * @param {Array<[number, object]>} timed - Pairs of arrival time in ms and event.
 * @returns {HTMLElement} The card.
 */
function cardWithTimedHistory(timed) {
    const card = cardWithHistory([]);
    timed.forEach(([at, event]) => updateAgentHistory(card, event, at));
    return card;
}

/**
 * Returns the rendered duration labels, top to bottom.
 * @param {Document} document - The modal document.
 * @returns {string[]} Each row's time-in-state text.
 */
function renderedDurations(document) {
    return [...document.querySelectorAll('.history-item')].map((item) => item.querySelector('.history-duration').textContent);
}

test('history records when each event arrived', () => {
    setupPage();

    const card = cardWithTimedHistory([[1000, { state: 'Acting', details: {} }]]);

    assert.equal(card.history[0].at, 1000);
});

test('each entry lasts until the next arrives, and the newest until now', () => {
    const history = [{ at: 9000 }, { at: 4000 }, { at: 1000 }];

    assert.deepEqual(historyDurations(history, 10000), [1000, 5000, 3000]);
});

test('a clock that went backwards reports zero rather than a negative duration', () => {
    assert.deepEqual(historyDurations([{ at: 5000 }], 4000), [0]);
});

test('durations read as seconds, minutes, and hours', () => {
    assert.equal(formatDuration(400), '<1s');
    assert.equal(formatDuration(14_900), '14s');
    assert.equal(formatDuration(125_000), '2m 05s');
    assert.equal(formatDuration(3_780_000), '1h 03m');
});

test('each row shows its time in state, the newest counting to now', (t) => {
    const document = setupPage();
    const realNow = Date.now;
    t.after(() => { Date.now = realNow; });
    Date.now = () => 20_000;
    const card = cardWithTimedHistory([
        [1000, { state: 'Thinking', details: { prompt: 'go' } }],
        [15_000, { state: 'Acting', details: { tool: 'shell' } }],
    ]);

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(renderedDurations(document), ['14s', '5s']);
});

test('each row carries a state color and a bar scaled to the longest shown', (t) => {
    const document = setupPage();
    const realNow = Date.now;
    t.after(() => { Date.now = realNow; });
    Date.now = () => 10_100;
    const card = cardWithTimedHistory([
        [0, { state: 'Thinking', details: {} }],
        [8000, { state: 'Waiting for Input', details: {} }],
        [9000, { state: 'Error', details: {} }],
        [10_000, { state: 'Idle', details: {} }],
    ]);

    openHistoryModal(KEY, { [KEY]: card });

    const rows = [...document.querySelectorAll('.history-item')];
    assert.deepEqual(rows.map((row) => row.className), [
        'history-item state-thinking',
        'history-item state-waiting',
        'history-item state-error',
        'history-item state-idle',
    ]);
    const widths = rows.map((row) => row.querySelector('.history-bar-fill').style.width);
    assert.deepEqual(widths, ['100%', '12.5%', '12.5%', '2%']);
    assert.equal(rows[0].querySelector('.history-bar').getAttribute('aria-hidden'), 'true');
});

test('a long-running newest entry does not shrink the finished bars', (t) => {
    const document = setupPage();
    const realNow = Date.now;
    t.after(() => { Date.now = realNow; });
    Date.now = () => 3_604_000;
    const card = cardWithTimedHistory([
        [0, { state: 'Acting', details: { tool: 'shell' } }],
        [2000, { state: 'Thinking', details: {} }],
        [4000, { state: 'Idle', details: {} }],
    ]);

    openHistoryModal(KEY, { [KEY]: card });

    const widths = [...document.querySelectorAll('.history-bar-fill')].map((fill) => fill.style.width);
    assert.deepEqual(widths, ['100%', '100%', '100%']);
    assert.deepEqual(renderedDurations(document), ['2s', '2s', '1h 00m']);
});

test('a refresh of the same entries updates rows in place', (t) => {
    const document = setupPage();
    const realNow = Date.now;
    t.after(() => { Date.now = realNow; });
    Date.now = () => 5000;
    const card = cardWithTimedHistory([
        [0, { state: 'Acting', details: { tool: 'shell' } }],
        [4000, { state: 'Idle', details: {} }],
    ]);
    openHistoryModal(KEY, { [KEY]: card });
    const before = [...document.querySelectorAll('.history-item')];

    Date.now = () => 7000;
    openHistoryModal(KEY, { [KEY]: card }, true);

    const after = [...document.querySelectorAll('.history-item')];
    assert.ok(after.every((row, index) => row === before[index]));
    assert.deepEqual(renderedDurations(document), ['4s', '3s']);
    assert.equal(after[1].querySelector('.history-bar-fill').style.width, '75%');
});

test('a new entry rebuilds the rows', (t) => {
    const document = setupPage();
    const realNow = Date.now;
    t.after(() => { Date.now = realNow; });
    Date.now = () => 5000;
    const card = cardWithTimedHistory([[0, { state: 'Acting', details: { tool: 'shell' } }]]);
    openHistoryModal(KEY, { [KEY]: card });
    const [first] = document.querySelectorAll('.history-item');

    updateAgentHistory(card, { state: 'Idle', details: {} }, 6000);
    openHistoryModal(KEY, { [KEY]: card }, true);

    const rows = [...document.querySelectorAll('.history-item')];
    assert.equal(rows.length, 2);
    assert.notEqual(rows[0], first);
});

test('an acting row and a reported tool duration get their own labels', () => {
    const document = setupPage();
    const card = cardWithTimedHistory([
        [Date.now(), { state: 'Acting', details: { tool: 'shell', duration: 3.2 } }],
    ]);

    openHistoryModal(KEY, { [KEY]: card });

    const row = document.querySelector('.history-item');
    assert.equal(row.className, 'history-item state-acting');
    assert.equal(row.querySelector('.history-tool-duration').textContent, 'tool 3.2s');
});

test('filtering keeps each row\'s duration from the full history', (t) => {
    const document = setupPage();
    const realNow = Date.now;
    t.after(() => { Date.now = realNow; });
    Date.now = () => 10_000;
    const card = cardWithTimedHistory([
        [0, { state: 'Error', details: { error: 'boom' } }],
        [4000, { state: 'Acting', details: { tool: 'shell' } }],
    ]);
    selectOption(document.getElementById('modal-state-filter'), 'Error');

    openHistoryModal(KEY, { [KEY]: card });

    assert.deepEqual(renderedDurations(document), ['4s']);
});

test('opening the pane grows it out of the card', () => {
    const document = setupPage();
    window.matchMedia = () => ({ matches: false });
    window.getComputedStyle = () => ({ getPropertyValue: () => '' });
    const card = cardWithHistory([]);
    card.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 50 });
    const content = document.querySelector('.modal-content');
    content.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 200 });
    const animated = [];
    content.animate = (keyframes) => animated.push(keyframes[0].transform);

    openHistoryModal(KEY, { [KEY]: card });
    openHistoryModal(KEY, { [KEY]: card }, true);

    assert.deepEqual(animated, ['translate(0px, 0px) scale(0.25, 0.25)']);
});

test('copying the path reports success', async () => {
    const copied = [];

    const outcome = await copyWorkspacePath({ copy_to_clipboard: async (path) => { copied.push(path); return true; } }, '/w');

    assert.deepEqual(copied, ['/w']);
    assert.equal(outcome, 'Copied!');
});

test('a refused, failed, or impossible copy reports failure', async (t) => {
    const realError = console.error;
    t.after(() => { console.error = realError; });
    const logged = [];
    console.error = (...args) => logged.push(args);

    assert.equal(await copyWorkspacePath({ copy_to_clipboard: async () => false }, '/w'), 'Copy failed');
    assert.equal(await copyWorkspacePath({ copy_to_clipboard: async () => { throw new Error('no clipboard'); } }, '/w'), 'Copy failed');
    assert.equal(await copyWorkspacePath(undefined, '/w'), 'Copy failed');
    assert.equal(await copyWorkspacePath({}, '/w'), 'Copy failed');
    assert.equal(logged.length, 1);
});
