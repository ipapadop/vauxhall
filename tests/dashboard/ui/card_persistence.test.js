// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { agents, clearAgents } from '../../../vauxhall/dashboard/ui/js/state.js';

const SHELL = {
    agent: 'Codex',
    workspace: '/home/user/project',
    session_id: 'one',
    state: 'Error',
    env: 'local',
    last_seen: Date.now(),
};

const PAGE = `
    <html><body>
        <div id="js-status"></div>
        <button id="clear-btn"></button>
        <button id="clear-stale-btn"></button>
        <input id="search-input" value="">
        <select id="sort-select">
            <option value="recent" selected>Recent</option>
            <option value="name">Name</option>
            <option value="status">Status</option>
            <option value="tokens">Tokens</option>
        </select>
        <input type="checkbox" id="attention-first-toggle">
        <input type="checkbox" id="notify-toggle">
        <div id="fleet-summary"></div>
        <div id="agent-grid"></div>
        <dialog id="history-modal">
            <button type="button" class="close-btn"></button>
            <div id="modal-agent-name"></div>
            <input id="modal-search" value="">
            <select id="modal-state-filter"><option value="ALL" selected>All</option></select>
            <div id="modal-history-body"></div>
        </dialog>
        <dialog id="card-menu-modal">
            <button type="button" id="card-menu-close"></button>
            <button type="button" id="card-menu-hide">Hide until next event</button>
            <button type="button" id="card-menu-denylist">Add agent to denylist</button>
        </dialog>
    </body></html>
`;

/**
 * Starts the dashboard against a fresh document and returns its test handles.
 * @param {import('node:test').TestContext} t - The test context, used to restore globals.
 * @param {object} [ipcOverrides] - Extra or replaced DashboardIPC bridge methods.
 * @returns {Promise<object>} The document and the captured backend callbacks.
 */
async function bootDashboard(t, ipcOverrides = {}) {
    const { document, window } = parseHTML(PAGE);
    const listeners = {};
    window.pyloid = {
        event: {
            listen(name, callback) {
                listeners[name] = callback;
            },
        },
    };
    window.ipc = {
        DashboardIPC: {
            ping: async () => true,
            set_ready: async () => true,
            get_stale_threshold: async () => 120,
            get_max_active_agents: async () => 100,
            get_saved_cards: async () => '[]',
            save_cards: async () => true,
            copy_to_clipboard: async () => true,
            get_settings: async () => JSON.stringify({ agent_denylist: [] }),
            save_settings: async () => JSON.stringify({ ok: true }),
            get_ui_state: async () => '{}',
            save_ui_state: async () => true,
            notify: async () => true,
            ...ipcOverrides,
        },
    };
    Object.defineProperty(document.getElementById('js-status'), 'innerText', {
        value: '',
        writable: true,
    });
    globalThis.document = document;
    globalThis.window = window;
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    const originalSetInterval = globalThis.setInterval;
    const originalAnimationFrame = globalThis.requestAnimationFrame;
    t.after(() => {
        globalThis.setInterval = originalSetInterval;
        globalThis.requestAnimationFrame = originalAnimationFrame;
        clearAgents();
    });
    globalThis.setInterval = () => 0;
    globalThis.requestAnimationFrame = (callback) => {
        callback();
        return 0;
    };
    clearAgents();

    await import(`../../../vauxhall/dashboard/ui/app.js?persistence=${Date.now()}${Math.random()}`);
    await new Promise((resolve) => setImmediate(resolve));

    return { document, listeners };
}

test('a saved card shell is restored into the grid on startup', async (t) => {
    const { document } = await bootDashboard(t, { get_saved_cards: async () => JSON.stringify([SHELL]) });

    const card = document.querySelector('.agent-card');
    assert.equal(card.querySelector('.agent-name').textContent, 'Codex');
    assert.equal(card.querySelector('.agent-workspace').textContent, '/home/user/project');
    assert.equal(card.querySelector('.status-badge').textContent, 'Error');
    assert.equal(card.classList.contains('error'), true);
    // No content is persisted, so a restored card shows no activity log yet.
    assert.equal(card.querySelector('.log-area').textContent, 'Ready...');
    assert.equal(document.querySelectorAll('.agent-card').length, 1);
});

test('a restored card long past the stale threshold shows STALE but still needs attention', async (t) => {
    const { document } = await bootDashboard(t, {
        get_saved_cards: async () => JSON.stringify([{ ...SHELL, last_seen: 100 }]),
    });

    const card = document.querySelector('.agent-card');
    // checkStaleness overwrites the badge, but the error class (read from
    // the persisted raw state) is left alone, so it still counts as
    // needing attention. See AGENTS.md's isAttentionCard note.
    assert.equal(card.querySelector('.status-badge').textContent, 'STALE');
    assert.equal(card.classList.contains('error'), true);
    assert.equal(card.classList.contains('stale'), true);
});

test('restore applies the configured stale threshold immediately, not the default', async (t) => {
    const { document } = await bootDashboard(t, {
        get_stale_threshold: async () => 10,
        get_saved_cards: async () => JSON.stringify([{ ...SHELL, last_seen: Date.now() - 20000 }]),
    });

    // The periodic staleness sweep is stubbed out in this harness, so this
    // only passes if restore itself checks staleness against the real
    // threshold rather than the 120s default.
    assert.equal(document.querySelector('.status-badge').textContent, 'STALE');
});

test('the history button on a restored, never-updated card opens an empty history', async (t) => {
    const { document } = await bootDashboard(t, { get_saved_cards: async () => JSON.stringify([SHELL]) });

    document.querySelector('.history-icon').click();

    assert.ok(document.getElementById('history-modal').hasAttribute('open'));
    assert.equal(document.querySelectorAll('.history-item').length, 0);
});

test('a live event for a restored identity updates the card instead of duplicating it', async (t) => {
    const { document, listeners } = await bootDashboard(t, {
        get_saved_cards: async () => JSON.stringify([SHELL]),
    });

    listeners['agent-update']({
        schema_version: 1,
        agent: 'Codex',
        workspace: '/home/user/project',
        session_id: 'one',
        state: 'Acting',
        details: { tool: 'shell', cmd: 'ls' },
    });

    assert.equal(document.querySelectorAll('.agent-card').length, 1);
    assert.equal(document.querySelector('.status-badge').textContent, 'Acting');
    assert.equal(document.querySelectorAll('.log-line').length, 1);
});

test('restored cards beyond the configured capacity are evicted', async (t) => {
    const older = { ...SHELL, session_id: 'older', last_seen: 100 };
    const newer = { ...SHELL, session_id: 'newer', last_seen: 200 };
    const { document } = await bootDashboard(t, {
        get_max_active_agents: async () => 1,
        get_saved_cards: async () => JSON.stringify([older, newer]),
    });

    assert.equal(document.querySelectorAll('.agent-card').length, 1);
    assert.equal(document.querySelector('.agent-session').title, 'newer');
});

test('a malformed saved-card response does not stop the dashboard from starting', async (t) => {
    const { document } = await bootDashboard(t, { get_saved_cards: async () => 'not json' });

    assert.equal(document.querySelectorAll('.agent-card').length, 0);
    assert.equal(document.getElementById('js-status').innerText, 'Connected to Agent Fleet');
});

test('a telemetry event schedules a debounced card save with identity only, never content', async (t) => {
    const payloads = [];
    const { listeners } = await bootDashboard(t, {
        save_cards: async (payload) => payloads.push(JSON.parse(payload)),
    });
    t.mock.timers.enable({ apis: ['setTimeout'] });

    listeners['agent-update']({
        schema_version: 1,
        agent: 'Codex',
        workspace: '/home/user/project',
        session_id: 'one',
        state: 'Waiting for Input',
        details: { prompt: 'Which secret should I use?' },
    });
    t.mock.timers.tick(500);
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(payloads.length, 1);
    assert.equal(payloads[0].length, 1);
    const { last_seen: lastSeen, ...rest } = payloads[0][0];
    assert.deepEqual(rest, {
        agent: 'Codex',
        workspace: '/home/user/project',
        session_id: 'one',
        state: 'Waiting for Input',
        env: 'local',
    });
    assert.ok(Number.isInteger(lastSeen) && lastSeen > 0);
    assert.equal(JSON.stringify(payloads[0]).includes('secret'), false);
});

test('clearing the grid schedules a save that empties the persisted list', async (t) => {
    const payloads = [];
    const { document, listeners } = await bootDashboard(t, {
        get_saved_cards: async () => JSON.stringify([SHELL]),
        save_cards: async (payload) => payloads.push(JSON.parse(payload)),
    });
    t.mock.timers.enable({ apis: ['setTimeout'] });
    listeners['agent-update']({ ...SHELL, schema_version: 1, session_id: 'two', details: {} });

    document.getElementById('clear-btn').click();
    t.mock.timers.tick(500);
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(payloads.at(-1), []);
    assert.deepEqual(Object.keys(agents), []);
});
