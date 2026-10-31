// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { createCard, openHistoryModal, updateCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

const ATTACK = '<img class="injected" src="x">';

/**
 * Give the test a fresh page holding the history modal.
 *
 * Called by each test rather than from a top-level beforeEach, which under
 * --test-isolation=none would run before every test in every file.
 */
function setupPage() {
    const { document, window } = parseHTML(`
        <html>
            <body>
                <dialog id="history-modal"></dialog>
                <div id="modal-agent-name"></div>
                <input id="modal-search" value="">
                <select id="modal-state-filter"><option value="ALL" selected>All</option></select>
                <div id="modal-history-body"></div>
            </body>
        </html>
    `);
    globalThis.document = document;
    globalThis.window = window;
}

test('agent identity and environment are rendered as inert text', () => {
    setupPage();
    const card = createCard(
        {
            agent: ATTACK,
            workspace: `/home/user/${ATTACK}`,
            session_id: ATTACK,
            env: `local${ATTACK}`,
        },
        () => {},
    );

    assert.equal(Boolean(card.querySelector('.injected')), false);
    assert.equal(card.querySelector('.agent-name').textContent, ATTACK);
    assert.equal(card.querySelector('.agent-workspace').textContent, `/home/user/${ATTACK}`);
    assert.equal(card.querySelector('.agent-session').textContent, `Session: ${ATTACK}`);
    assert.equal(card.querySelector('.env-badge').textContent, 'local');
    assert.equal(card.querySelector('.env-badge').className, 'env-badge env-local');
});

test('activity details and metrics are rendered without creating markup', () => {
    setupPage();
    const card = createCard(
        { agent: 'Agent', workspace: '/workspace', env: 'local' },
        () => {},
    );

    updateCard(card, {
        state: ATTACK,
        details: {
            tool: ATTACK,
            cmd: ATTACK,
            tokens: ATTACK,
            duration: ATTACK,
        },
    });

    assert.equal(Boolean(card.querySelector('.injected')), false);
    assert.equal(card.querySelector('.status-badge').textContent, ATTACK);
    assert.match(card.querySelector('.log-area').textContent, new RegExp(ATTACK));
    assert.equal(Boolean(card.querySelector('.metric-badge')), false);
});

test('assistant messages appear as inert text in the activity log', () => {
    setupPage();
    const card = createCard({ agent: 'Codex', workspace: '/workspace', session_id: 'session' }, () => {});

    updateCard(card, { state: 'Thinking', details: { message: ATTACK } });

    assert.equal(Boolean(card.querySelector('.injected')), false);
    assert.match(card.querySelector('.log-area').textContent, /Agent:/);
    assert.match(card.querySelector('.log-area').textContent, new RegExp(ATTACK));
});

test('history details are rendered without creating markup', () => {
    setupPage();
    const card = createCard(
        { agent: 'Agent', workspace: '/workspace', env: 'local' },
        () => {},
    );
    card.history = [
        {
            time: '12:00:00',
            state: ATTACK,
            details: { prompt: ATTACK },
        },
    ];

    openHistoryModal('Agent:/workspace', { 'Agent:/workspace': card });

    const history = document.getElementById('modal-history-body');
    assert.equal(Boolean(history.querySelector('.injected')), false);
    assert.equal(history.querySelector('.history-state').textContent, ATTACK);
    assert.match(history.textContent, new RegExp(ATTACK));
});

// The content security policy allows no inline styles or scripts, so markup
// that uses them would render unstyled or not run.
test('the page uses no inline styles, scripts, or event handler attributes', () => {
    const html = readFileSync(new URL('../../../vauxhall/dashboard/ui/index.html', import.meta.url), 'utf8');
    const { document } = parseHTML(html);

    assert.deepEqual([...document.querySelectorAll('[style]')].map((element) => element.outerHTML), []);
    assert.deepEqual([...document.querySelectorAll('script:not([src])')].map((element) => element.outerHTML), []);
    const handlers = [...document.querySelectorAll('*')].flatMap((element) =>
        element.getAttributeNames().filter((name) => name.startsWith('on')));
    assert.deepEqual(handlers, []);
});

test('the card template uses no inline styles', () => {
    setupPage();
    const card = createCard({ agent: 'codex', workspace: '/home/user/project', session_id: 's1' }, () => {});

    assert.deepEqual([...card.querySelectorAll('[style]')].map((element) => element.outerHTML), []);
});
