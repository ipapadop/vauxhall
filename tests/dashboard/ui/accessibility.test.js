// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { closeDialog, openDialog } from '../../../vauxhall/dashboard/ui/js/dialog.js';
import { initInstall } from '../../../vauxhall/dashboard/ui/js/install.js';
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
 * Builds a card that records the controls reported by its pane and menu callbacks.
 * @returns {{card: HTMLElement, opened: HTMLElement[], menuOpened: HTMLElement[]}}
 *   The card and what it reported.
 */
function cardWithCallbacks() {
    const opened = [];
    const menuOpened = [];
    const card = createCard({ ...IDENTITY }, (opener) => opened.push(opener), (opener) => menuOpened.push(opener));
    return { card, opened, menuOpened };
}

test('the workspace and menu controls are buttons with accessible names', () => {
    setupPage();
    const { card } = cardWithCallbacks();

    const workspace = card.querySelector('.agent-workspace');
    const menu = card.querySelector('.menu-icon');

    assert.equal(workspace.tagName, 'BUTTON');
    assert.equal(workspace.getAttribute('type'), 'button');
    assert.equal(workspace.textContent, IDENTITY.workspace);
    assert.equal(workspace.getAttribute('aria-label'), 'Open activity for Codex in /home/user/project, session session-1');
    // The dashboard only monitors: nothing on a card sends to the agent.
    assert.equal(card.querySelector('.prompt-icon'), null);
    assert.equal(menu.tagName, 'BUTTON');
    assert.equal(menu.getAttribute('type'), 'button');
    assert.equal(menu.getAttribute('aria-label'), 'Options for Codex in /home/user/project, session session-1');
});

test('activating the menu button reports it as the control to focus again', () => {
    setupPage();
    const { card, menuOpened } = cardWithCallbacks();
    const menu = card.querySelector('.menu-icon');

    menu.click();

    assert.deepEqual(menuOpened, [menu]);
});

test('each card names its session, so concurrent sessions stay distinguishable', () => {
    setupPage();
    const same = { agent: 'Codex', workspace: '/home/user/project' };
    const first = createCard({ ...same, session_id: 'one' }, () => {});
    const second = createCard({ ...same, session_id: 'two' }, () => {});

    assert.equal(first.getAttribute('role'), 'group');
    assert.equal(first.getAttribute('aria-label'), 'Codex session one');
    assert.notEqual(
        first.querySelector('.agent-workspace').getAttribute('aria-label'),
        second.querySelector('.agent-workspace').getAttribute('aria-label'),
    );
});

test('activating the workspace button opens the pane once, reporting it as the control to focus again', () => {
    setupPage();
    const { card, opened } = cardWithCallbacks();
    const workspace = card.querySelector('.agent-workspace');

    workspace.click();

    assert.deepEqual(opened, [workspace]);
});

test('clicking the card opens the pane with the workspace button to focus again', () => {
    setupPage();
    const { card, opened } = cardWithCallbacks();

    card.click();

    assert.deepEqual(opened, [card.querySelector('.agent-workspace')]);
});

test('the menu button does not open the pane', () => {
    setupPage();
    const { card, opened } = cardWithCallbacks();

    card.querySelector('.menu-icon').click();

    assert.deepEqual(opened, []);
});

test('the pane has a named Copy path button, a polite status, and focuses its filter', () => {
    const html = readFileSync(new URL('../../../vauxhall/dashboard/ui/index.html', import.meta.url), 'utf8');
    const { document } = parseHTML(html);

    const pane = document.getElementById('history-modal');
    const copy = pane.querySelector('#modal-copy-path');
    const status = pane.querySelector('#modal-copy-status');
    assert.equal(pane.tagName, 'DIALOG');
    assert.equal(copy.tagName, 'BUTTON');
    assert.equal(copy.getAttribute('type'), 'button');
    assert.equal(copy.textContent, 'Copy path');
    assert.equal(status.getAttribute('role'), 'status');
    assert.equal(status.getAttribute('aria-live'), 'polite');
    // The filter, not Copy path, takes focus on open, as before the pane had a copy button.
    assert.ok(pane.querySelector('#modal-search').hasAttribute('autofocus'));
    // The dashboard only monitors: the pane has nowhere to type to the agent.
    assert.equal(pane.querySelector('textarea'), null);
    assert.equal(document.getElementById('prompt-modal'), null);
});

/**
 * Fills a grid with two cards that a name sort has to swap.
 * @param {HTMLElement} grid - The agent grid.
 */
function addUnsortedCards(grid) {
    for (const agent of ['Gemini', 'Claude']) {
        const card = createCard({ agent, workspace: `/home/user/${agent}`, session_id: agent }, () => {});
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

/**
 * Loads the real dashboard page, rather than a synthetic fragment, since
 * these checks are about the static markup itself.
 * @returns {Document} The parsed index.html document.
 */
function loadIndexPage() {
    const html = readFileSync(new URL('../../../vauxhall/dashboard/ui/index.html', import.meta.url), 'utf8');
    return parseHTML(html).document;
}

test('the fleet summary is a polite live region', () => {
    const document = loadIndexPage();
    const summary = document.getElementById('fleet-summary');

    assert.equal(summary.getAttribute('role'), 'status');
    assert.equal(summary.getAttribute('aria-live'), 'polite');
});

test('app actions trail the title, and view controls precede the clear actions', () => {
    const document = loadIndexPage();
    const ids = (selector) => [...document.querySelectorAll(`${selector} [id]`)].map(el => el.id);

    assert.deepEqual(ids('.app-actions'), ['install-hooks-btn', 'theme-toggle', 'settings-btn']);
    assert.deepEqual(ids('.view-bar'), [
        'search-input', 'sort-select', 'attention-first-toggle', 'notify-toggle', 'clear-stale-btn', 'clear-btn',
    ]);
    assert.ok(document.getElementById('install-hooks-btn').classList.contains('primary-btn'));
    assert.ok(document.getElementById('clear-btn').classList.contains('danger-btn'));
});

test('the attention-first and notify toggles are checkboxes named by a wrapping label', () => {
    const document = loadIndexPage();

    for (const id of ['attention-first-toggle', 'notify-toggle']) {
        const checkbox = document.getElementById(id);
        assert.equal(checkbox.getAttribute('type'), 'checkbox');
        const label = checkbox.closest('label');
        assert.ok(label, `${id} is not inside a label`);
        assert.ok(label.textContent.trim().length > 0, `${id}'s label has no text`);
    }
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

test('the Install Hooks button is named and opens a labeled modal dialog', () => {
    const document = loadIndexPage();
    const button = document.getElementById('install-hooks-btn');
    const dialog = document.getElementById('install-dialog');

    assert.equal(button.tagName, 'BUTTON');
    assert.equal(button.textContent.trim(), 'Install Hooks…');
    assert.equal(button.getAttribute('aria-haspopup'), 'dialog');
    assert.equal(dialog.tagName, 'DIALOG');
    assert.equal(document.getElementById(dialog.getAttribute('aria-labelledby')).textContent, 'Install Hooks');
    for (const id of ['install-run', 'install-another', 'install-close']) {
        const control = document.getElementById(id);
        assert.equal(control.tagName, 'BUTTON', id);
        assert.equal(control.getAttribute('type'), 'button', id);
        assert.ok(control.textContent.trim(), `${id} has no text`);
    }
});

test('the install log and outcome are live regions, and errors are alerts', () => {
    const document = loadIndexPage();

    assert.equal(document.getElementById('install-log').getAttribute('role'), 'log');
    assert.equal(document.getElementById('install-log').getAttribute('aria-live'), 'polite');
    assert.equal(document.getElementById('install-outcome').getAttribute('role'), 'status');
    assert.equal(document.getElementById('install-error').getAttribute('role'), 'alert');
    assert.equal(document.getElementById('install-agents').tagName, 'FIELDSET');
    assert.ok(document.querySelector('#install-agents > legend').textContent.trim());
});

test('each install agent checkbox is named by a label for it', async (t) => {
    const document = loadIndexPage();
    const saved = { document: globalThis.document, window: globalThis.window };
    globalThis.document = document;
    t.after(() => Object.assign(globalThis, saved));
    const agents = [
        { agent: 'claude', name: 'Claude Code', detected: true, installed: false, error: null },
        { agent: 'gemini', name: 'Gemini', detected: false, installed: false, error: null },
    ];
    initInstall({ select_install_directory: async () => JSON.stringify({ ok: true, path: '/w', agents }) });

    document.getElementById('install-hooks-btn').dispatchEvent(new document.defaultView.Event('click'));
    await new Promise(resolve => setTimeout(resolve, 0));

    const boxes = document.querySelectorAll('#install-agents input[type="checkbox"]');
    assert.equal(boxes.length, 2);
    for (const box of boxes) {
        const label = document.querySelector(`label[for="${box.id}"]`);
        assert.ok(label?.textContent.trim(), `${box.id} has no label`);
    }
});
