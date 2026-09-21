// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { closeDialog, openDialog } from '../../../vauxhall/dashboard/ui/js/dialog.js';
import { createCard, sortGrid, updateCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

const IDENTITY = { agent: 'Codex', workspace: '/home/user/project', session_id: 'session-1' };

/**
 * Builds a grid page. Called from each test rather than a shared hook, so a
 * hook in another test file cannot replace the document mid-test.
 * @returns {Document} The grid document.
 */
function setupPage() {
    const { document, window } = parseHTML('<html><body><div id="agent-grid"></div><dialog id="dialog"></dialog></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    return document;
}

/**
 * Builds a card that records every workspace path copied through it.
 * @returns {{card: HTMLElement, clipboard: string[], opened: HTMLElement[]}} The card and what it reported.
 */
function cardWithClipboard() {
    const clipboard = [];
    const opened = [];
    const ipc = { DashboardIPC: { copy_to_clipboard: async (path) => { clipboard.push(path); return true; } } };
    const card = createCard({ ...IDENTITY }, ipc, (opener) => opened.push(opener));
    return { card, clipboard, opened };
}

test('the workspace and history controls are buttons with accessible names', () => {
    setupPage();
    const { card } = cardWithClipboard();

    const workspace = card.querySelector('.agent-workspace');
    const history = card.querySelector('.history-icon');

    assert.equal(workspace.tagName, 'BUTTON');
    assert.equal(workspace.getAttribute('type'), 'button');
    assert.equal(workspace.textContent, IDENTITY.workspace);
    assert.equal(history.tagName, 'BUTTON');
    assert.equal(history.getAttribute('type'), 'button');
    assert.equal(history.getAttribute('aria-label'), 'View history for Codex');
});

test('activating the workspace button copies the path exactly once', async () => {
    setupPage();
    const { card, clipboard } = cardWithClipboard();

    card.querySelector('.agent-workspace').click();
    await Promise.resolve();

    assert.deepEqual(clipboard, [IDENTITY.workspace]);
});

test('activating the history button reports it as the control to focus again', () => {
    setupPage();
    const { card, opened } = cardWithClipboard();
    const history = card.querySelector('.history-icon');

    history.click();

    assert.deepEqual(opened, [history]);
});

/**
 * Fills a grid with two cards that a name sort has to swap.
 * @param {HTMLElement} grid - The agent grid.
 */
function addUnsortedCards(grid) {
    for (const agent of ['Gemini', 'Claude']) {
        const card = createCard({ agent, workspace: `/home/user/${agent}`, session_id: agent }, null, () => {});
        updateCard(card, { state: 'Idle', details: { status: 'Idle' } });
        grid.appendChild(card);
    }
}

test('sorting skips the move animation when reduced motion is preferred', (t) => {
    const document = setupPage();
    const grid = document.getElementById('agent-grid');
    addUnsortedCards(grid);
    let frames = 0;
    const originalAnimationFrame = globalThis.requestAnimationFrame;
    t.after(() => {
        globalThis.requestAnimationFrame = originalAnimationFrame;
    });
    globalThis.requestAnimationFrame = (callback) => {
        frames++;
        callback();
        return 0;
    };
    globalThis.window.matchMedia = (query) => ({ matches: query === '(prefers-reduced-motion: reduce)' });

    sortGrid('name', grid);

    assert.equal(frames, 0);
    assert.deepEqual([...grid.children].map((card) => card.querySelector('.agent-name').textContent), ['Claude', 'Gemini']);
});

test('sorting animates the move when motion is not restricted', (t) => {
    const document = setupPage();
    const grid = document.getElementById('agent-grid');
    addUnsortedCards(grid);
    let frames = 0;
    const originalAnimationFrame = globalThis.requestAnimationFrame;
    t.after(() => {
        globalThis.requestAnimationFrame = originalAnimationFrame;
    });
    globalThis.requestAnimationFrame = (callback) => {
        frames++;
        callback();
        return 0;
    };
    globalThis.window.matchMedia = () => ({ matches: false });

    sortGrid('name', grid);

    assert.equal(frames, 1);
});

test('a dialog with native support is shown modally, and only once', () => {
    const document = setupPage();
    const dialog = document.getElementById('dialog');
    let shown = 0;
    dialog.showModal = () => { shown++; dialog.open = true; };

    openDialog(dialog);
    openDialog(dialog);

    assert.equal(shown, 1);
});

test('a dialog with native support is closed through close()', () => {
    const document = setupPage();
    const dialog = document.getElementById('dialog');
    let closed = 0;
    dialog.close = () => { closed++; };

    closeDialog(dialog);

    assert.equal(closed, 1);
});

test('without native support the open attribute stands in and still reports closing', () => {
    const document = setupPage();
    const dialog = document.getElementById('dialog');
    let closes = 0;
    dialog.addEventListener('close', () => { closes++; });

    openDialog(dialog);
    assert.ok(dialog.hasAttribute('open'));

    closeDialog(dialog);
    assert.ok(!dialog.hasAttribute('open'));
    assert.equal(closes, 1);

    // Closing an already closed dialog reports nothing.
    closeDialog(dialog);
    assert.equal(closes, 1);
});
