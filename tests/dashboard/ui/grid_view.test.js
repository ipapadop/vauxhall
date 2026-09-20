// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { createCard, filterGrid, sortGrid, updateCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

let document;
let grid;

/**
 * Builds an empty grid page. Called from each test rather than a shared hook,
 * so a hook in another test file cannot replace the document mid-test.
 * @param {import('node:test').TestContext} t - The test context, used to restore globals.
 */
function setupGrid(t) {
    const parsed = parseHTML('<html><body><div id="agent-grid"></div></body></html>');
    document = parsed.document;
    globalThis.document = document;
    globalThis.window = parsed.window;
    // sortGrid measures positions around the re-order to animate the move.
    // linkedom reports every card at the origin, so the animation is a no-op.
    const originalAnimationFrame = globalThis.requestAnimationFrame;
    t.after(() => {
        globalThis.requestAnimationFrame = originalAnimationFrame;
    });
    globalThis.requestAnimationFrame = (callback) => {
        callback();
        return 0;
    };
    grid = document.getElementById('agent-grid');
}

/**
 * Adds a card to the grid.
 * @param {object} options - The card's identity, state, and metrics.
 * @param {string} options.agent - The agent name.
 * @param {string} [options.workspace] - The workspace path.
 * @param {string} [options.state] - The state to report.
 * @param {number} [options.lastSeen] - The last seen timestamp.
 * @param {number} [options.tokens] - The token count to report.
 * @returns {HTMLElement} The created card.
 */
function addCard({ agent, workspace = `/home/user/${agent}`, state = 'Idle', lastSeen = 0, tokens }) {
    const card = createCard({ agent, workspace, session_id: agent }, null, () => {});
    card.dataset.lastSeen = String(lastSeen);
    updateCard(card, { state, details: { status: state, tokens } });
    grid.appendChild(card);
    return card;
}

/**
 * Returns the agent names in the grid, in display order.
 * @returns {string[]} The ordered agent names.
 */
function order() {
    return [...grid.children].map((card) => card.querySelector('.agent-name').textContent);
}

test('sorting by name orders cards alphabetically', (t) => {
    setupGrid(t);
    addCard({ agent: 'Gemini' });
    addCard({ agent: 'Claude' });
    addCard({ agent: 'Codex' });

    sortGrid('name', grid);

    assert.deepEqual(order(), ['Claude', 'Codex', 'Gemini']);
});

test('sorting by recent puts the most recently seen card first', (t) => {
    setupGrid(t);
    addCard({ agent: 'Stale', lastSeen: 100 });
    addCard({ agent: 'Fresh', lastSeen: 300 });
    addCard({ agent: 'Middle', lastSeen: 200 });

    sortGrid('recent', grid);

    assert.deepEqual(order(), ['Fresh', 'Middle', 'Stale']);
});

test('sorting by status puts the cards that need attention first', (t) => {
    setupGrid(t);
    addCard({ agent: 'Idle', state: 'Idle' });
    addCard({ agent: 'Acting', state: 'Acting' });
    addCard({ agent: 'Failed', state: 'Error' });
    addCard({ agent: 'Blocked', state: 'Input Required' });

    sortGrid('status', grid);

    assert.deepEqual(order(), ['Failed', 'Blocked', 'Acting', 'Idle']);
});

test('sorting by status ranks a stale card last', (t) => {
    setupGrid(t);
    const stale = addCard({ agent: 'Gone', state: 'Acting' });
    stale.querySelector('.status-badge').textContent = 'STALE';
    addCard({ agent: 'Working', state: 'Acting' });
    addCard({ agent: 'Resting', state: 'Idle' });

    sortGrid('status', grid);

    assert.deepEqual(order(), ['Working', 'Resting', 'Gone']);
});

test('sorting by status ranks an unrecognized badge after every known one', (t) => {
    setupGrid(t);
    const unknown = addCard({ agent: 'Mystery', state: 'Idle' });
    unknown.querySelector('.status-badge').textContent = 'Reticulating';
    addCard({ agent: 'Resting', state: 'Idle' });

    sortGrid('status', grid);

    assert.deepEqual(order(), ['Resting', 'Mystery']);
});

test('sorting by tokens puts the largest count first and treats a missing badge as zero', (t) => {
    setupGrid(t);
    addCard({ agent: 'Small', state: 'Acting', tokens: 120 });
    addCard({ agent: 'Silent', state: 'Acting' });
    addCard({ agent: 'Large', state: 'Acting', tokens: 48000 });

    sortGrid('tokens', grid);

    assert.deepEqual(order(), ['Large', 'Small', 'Silent']);
});

test('sorting by tokens uses the exact count, not the abbreviated badge text', (t) => {
    setupGrid(t);
    addCard({ agent: 'Bigger', state: 'Acting', tokens: 9600 });
    addCard({ agent: 'Biggest', state: 'Acting', tokens: 11000 });

    sortGrid('tokens', grid);

    assert.deepEqual(order(), ['Biggest', 'Bigger']);
});

test('an unknown sort criterion leaves the order unchanged', (t) => {
    setupGrid(t);
    addCard({ agent: 'Gemini' });
    addCard({ agent: 'Claude' });

    sortGrid('toString', grid);

    assert.deepEqual(order(), ['Gemini', 'Claude']);
});

test('sorting an empty grid does nothing', (t) => {
    setupGrid(t);
    sortGrid('name', grid);

    assert.deepEqual(order(), []);
});

test('search matches the agent name and hides the rest', (t) => {
    setupGrid(t);
    const agents = {
        claude: addCard({ agent: 'Claude' }),
        codex: addCard({ agent: 'Codex' }),
    };

    filterGrid('codex', agents);

    assert.equal(agents.codex.style.display, 'flex');
    assert.equal(agents.claude.style.display, 'none');
});

test('search matches the workspace path', (t) => {
    setupGrid(t);
    const agents = {
        api: addCard({ agent: 'Claude', workspace: '/home/user/api-server' }),
        web: addCard({ agent: 'Codex', workspace: '/home/user/web-client' }),
    };

    filterGrid('api-server', agents);

    assert.equal(agents.api.style.display, 'flex');
    assert.equal(agents.web.style.display, 'none');
});

test('search ignores case because the query is lowercased', (t) => {
    setupGrid(t);
    const agents = { claude: addCard({ agent: 'Claude' }) };

    filterGrid('claude', agents);

    assert.equal(agents.claude.style.display, 'flex');
});

test('an empty query shows every card again', (t) => {
    setupGrid(t);
    const agents = {
        claude: addCard({ agent: 'Claude' }),
        codex: addCard({ agent: 'Codex' }),
    };
    filterGrid('codex', agents);

    filterGrid('', agents);

    assert.deepEqual(Object.values(agents).map((card) => card.style.display), ['flex', 'flex']);
});

test('a query matching nothing hides every card', (t) => {
    setupGrid(t);
    const agents = {
        claude: addCard({ agent: 'Claude' }),
        codex: addCard({ agent: 'Codex' }),
    };

    filterGrid('nothing-matches-this', agents);

    assert.deepEqual(Object.values(agents).map((card) => card.style.display), ['none', 'none']);
});

test('search leaves a card without name or workspace elements alone', (t) => {
    setupGrid(t);
    const bare = document.createElement('div');
    bare.style.display = 'flex';

    filterGrid('anything', { bare });

    assert.equal(bare.style.display, 'flex');
});
