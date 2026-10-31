// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { addToDenylist } from '../../../vauxhall/dashboard/ui/js/denylist.js';
import { createFleet } from '../../../vauxhall/dashboard/ui/js/fleet.js';
import { agentKey, agents, clearAgents, isHidden, setHidden } from '../../../vauxhall/dashboard/ui/js/state.js';

/**
 * Returns a telemetry event for a session.
 * @param {string} session - The session ID.
 * @param {object} [overrides] - Fields replacing the defaults.
 * @returns {object} The event.
 */
function event(session, overrides = {}) {
    return { agent: 'Codex', workspace: '/home/user/project', session_id: session, state: 'Acting', details: { tool: 'Bash' }, ...overrides };
}

/**
 * Builds a page and a fleet over its grid, recording removals. The page is
 * built from each test, and the shared card state cleared after it.
 * @param {object} t - The test context.
 * @returns {{fleet: object, grid: HTMLElement, removed: string[][]}} The fleet,
 *   its grid, and each batch of keys passed to `onRemoved`.
 */
function makeFleet(t) {
    const { document, window } = parseHTML('<html><body><div id="agent-grid"></div></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    clearAgents();
    t.after(clearAgents);
    const grid = document.getElementById('agent-grid');
    const removed = [];
    const fleet = createFleet(grid, {
        openPane: () => {},
        openMenu: () => {},
        onRemoved: (keys) => removed.push(keys),
    });
    return { fleet, grid, removed };
}

test('an event for a new session adds its card', (t) => {
    const { fleet, grid, removed } = makeFleet(t);

    const update = fleet.apply(event('s1'), 10);

    assert.equal(update.key, agentKey(event('s1')));
    assert.equal(update.enteredAttention, false);
    assert.equal(grid.children.length, 1);
    assert.equal(agents[update.key].history.length, 1);
    assert.deepEqual(removed, [[]]);
});

test('a new card at the limit evicts the least recently seen one', (t) => {
    const { fleet, removed } = makeFleet(t);
    fleet.apply(event('old'), 1);
    agents[agentKey(event('old'))].dataset.lastSeen = '1';

    fleet.apply(event('new'), 1);

    assert.deepEqual(Object.keys(agents), [agentKey(event('new'))]);
    assert.deepEqual(removed.at(-1), [agentKey(event('old'))]);
});

test('an event for a hidden card shows it again', (t) => {
    const { fleet } = makeFleet(t);
    const { key } = fleet.apply(event('s1'), 10);
    setHidden(agents[key], true);

    fleet.apply(event('s1'), 10);

    assert.equal(isHidden(agents[key]), false);
});

test('a replaced session removes its card, and creates none when absent', (t) => {
    const { fleet, grid, removed } = makeFleet(t);
    const cleared = event('s1', { state: 'Idle', details: { status: 'session cleared', end_reason: 'clear' } });

    assert.equal(fleet.apply(cleared, 10), null);
    const { key } = fleet.apply(event('s1'), 10);
    assert.deepEqual(fleet.apply(cleared, 10), { key, removed: true });

    assert.equal(grid.children.length, 0);
    assert.equal(agents[key], undefined);
    assert.deepEqual(removed.at(-1), [key]);
});

test('a late copy of an idle card\'s final message changes nothing', (t) => {
    const { fleet, grid } = makeFleet(t);
    fleet.apply(event('s1', { state: 'Idle', details: { status: 'Ready', message: 'Done' } }), 10);

    assert.equal(fleet.apply(event('s1', { state: 'Thinking', details: { message: 'Done' } }), 10), null);

    assert.equal(grid.firstElementChild.querySelector('.status-badge').textContent, 'Idle');
});

test('restore keeps the newest saved cards within the limit and skips existing ones', (t) => {
    const { fleet, grid } = makeFleet(t);
    fleet.apply(event('live'), 10);
    const saved = [
        { ...event('oldest'), last_seen: 1 },
        { ...event('live'), last_seen: 5, state: 'Error' },
        { ...event('newest'), last_seen: 9 },
    ];

    fleet.restore(saved, 2);

    assert.equal(grid.children.length, 2);
    assert.equal(agents[agentKey(event('newest'))].dataset.lastSeen, '9');
    assert.equal(agents[agentKey(event('live'))].dataset.state, 'Acting');
    assert.equal(agents[agentKey(event('oldest'))], undefined);
});

test('restore ignores saved data that is not a list', (t) => {
    const { fleet, grid } = makeFleet(t);

    fleet.restore({ cards: [] }, 10);
    fleet.restore([{ ...event('s1') }], -1);

    assert.equal(grid.children.length, 0);
});

test('settings remove denylisted cards before evicting to the limit', (t) => {
    const { fleet, removed } = makeFleet(t);
    fleet.apply(event('a', { agent: 'Gemini' }), 10);
    fleet.apply(event('b'), 10);
    fleet.apply(event('c'), 10);
    agents[agentKey(event('b'))].dataset.lastSeen = '1';

    fleet.applySettings(['Gemini'], 1);

    assert.deepEqual(Object.keys(agents), [agentKey(event('c'))]);
    assert.deepEqual(removed.slice(-2), [[agentKey(event('a', { agent: 'Gemini' }))], [agentKey(event('b'))]]);
});

test('clearing stale cards removes only those, and clearing removes all', (t) => {
    const { fleet, grid } = makeFleet(t);
    fleet.apply(event('stale'), 10);
    fleet.apply(event('fresh'), 10);
    agents[agentKey(event('stale'))].classList.add('stale');

    fleet.removeStale();
    assert.deepEqual(Object.keys(agents), [agentKey(event('fresh'))]);

    fleet.clear();
    assert.equal(grid.children.length, 0);
    assert.deepEqual(Object.keys(agents), []);
});

/**
 * Builds a settings bridge that records saved denylists.
 * @param {object|Error} settings - What `get_settings` returns, or throws.
 * @param {object} [saveResult] - What `save_settings` returns.
 * @returns {{ipc: object, saved: string[][]}} The bridge and the saved lists.
 */
function denylistBridge(settings, saveResult = { ok: true }) {
    const saved = [];
    const ipc = {
        get_settings: async () => {
            if (settings instanceof Error) throw settings;
            return JSON.stringify(settings);
        },
        save_settings: async (payload) => {
            saved.push(JSON.parse(payload).changes.dashboard.agent_denylist);
            return JSON.stringify(saveResult);
        },
    };
    return { ipc, saved };
}

test('adding to the denylist appends the agent once', async () => {
    const { ipc, saved } = denylistBridge({ agent_denylist: ['Gemini'] });

    await addToDenylist(ipc, 'Codex');
    await addToDenylist(denylistBridge({ agent_denylist: ['Codex'] }).ipc, 'Codex');

    assert.deepEqual(saved, [['Gemini', 'Codex']]);
});

test('the denylist is not saved when settings can\'t be read or changed', async (t) => {
    const errors = t.mock.method(console, 'error', () => {});
    const cases = [
        denylistBridge({ error: 'unreadable' }),
        denylistBridge({ agent_denylist: [], agent_denylist_editable: false }),
        denylistBridge(new Error('bridge gone')),
    ];
    const rejected = denylistBridge({}, { ok: false, error: 'bad' });

    for (const { ipc } of [...cases, rejected]) await addToDenylist(ipc, 'Codex');

    assert.deepEqual(cases.map(({ saved }) => saved), [[], [], []]);
    assert.deepEqual(rejected.saved, [['Codex']]);
    assert.equal(errors.mock.callCount(), 4);
});
