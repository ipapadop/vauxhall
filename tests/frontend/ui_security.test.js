// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';

import { parseHTML } from 'linkedom';

import { createCard, openHistoryModal, updateCard } from '../../vauxhall/dashboard/ui/js/ui.js';

const ATTACK = '<img class="injected" src="x">';

beforeEach(() => {
    const { document, window } = parseHTML(`
        <html>
            <body>
                <div id="history-modal"></div>
                <div id="modal-agent-name"></div>
                <input id="modal-search" value="">
                <select id="modal-state-filter"><option value="ALL" selected>All</option></select>
                <div id="modal-history-body"></div>
            </body>
        </html>
    `);
    globalThis.document = document;
    globalThis.window = window;
});

test('agent identity and environment are rendered as inert text', () => {
    const card = createCard(
        {
            agent: ATTACK,
            workspace: `/home/user/${ATTACK}`,
            env: `local${ATTACK}`,
        },
        null,
        () => {},
    );

    assert.equal(Boolean(card.querySelector('.injected')), false);
    assert.equal(card.querySelector('.agent-name').textContent, ATTACK);
    assert.equal(card.querySelector('.agent-workspace').textContent, `/home/user/${ATTACK}`);
    assert.equal(card.querySelector('.env-badge').textContent, 'local');
    assert.equal(card.querySelector('.env-badge').className, 'env-badge env-local');
});

test('activity details and metrics are rendered without creating markup', () => {
    const card = createCard(
        { agent: 'Agent', workspace: '/workspace', env: 'local' },
        null,
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

test('history details are rendered without creating markup', () => {
    const card = createCard(
        { agent: 'Agent', workspace: '/workspace', env: 'local' },
        null,
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
