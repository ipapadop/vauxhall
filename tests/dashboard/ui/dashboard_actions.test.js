// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { agents, clearAgents } from '../../../vauxhall/dashboard/ui/js/state.js';
import { createCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

const BASE = {
    schema_version: 1,
    agent: 'Codex',
    workspace: '/home/user/project',
    state: 'Thinking',
    details: {},
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
    const clipboard = [];
    window.ipc = {
        DashboardIPC: {
            ping: async () => true,
            set_ready: async () => true,
            get_stale_threshold: async () => 120,
            get_max_active_agents: async () => 100,
            copy_to_clipboard: async (path) => {
                clipboard.push(path);
                return true;
            },
            get_settings: async () => JSON.stringify({ agent_denylist: [] }),
            save_settings: async () => JSON.stringify({ ok: true }),
            ...ipcOverrides,
        },
    };
    // linkedom exposes innerText as a getter, so the status line the dashboard
    // writes to needs a writable one.
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

    await import(`../../../vauxhall/dashboard/ui/app.js?actions=${Date.now()}${Math.random()}`);
    await new Promise((resolve) => setImmediate(resolve));

    return { document, clipboard, listeners };
}

/**
 * Chooses an option in a select, the way clicking it would.
 * @param {HTMLSelectElement} select - The select element.
 * @param {string} value - The value of the option to choose.
 */
function choose(select, value) {
    // Deselecting an option after selecting another clears the selection in
    // linkedom, so the choice is made only once nothing else is selected.
    for (const option of select.options) option.selected = false;
    for (const option of select.options) {
        if (option.value === value) option.selected = true;
    }
}

/**
 * Returns the agent names shown in the grid, in display order.
 * @param {Document} document - The dashboard document.
 * @returns {string[]} The ordered agent names.
 */
function order(document) {
    return [...document.getElementById('agent-grid').children].map(
        (card) => card.querySelector('.agent-name').textContent,
    );
}

test('clear removes every card from the grid and the state', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });
    listeners['agent-update']({ ...BASE, session_id: 'two' });

    document.getElementById('clear-btn').click();

    assert.equal(document.getElementById('agent-grid').children.length, 0);
    assert.deepEqual(Object.keys(agents), []);
});

test('clear stale removes only the cards that went stale', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'gone' });
    listeners['agent-update']({ ...BASE, session_id: 'here' });
    const staleKey = '["Codex","/home/user/project","gone"]';
    agents[staleKey].dataset.lastSeen = String(Date.now() - 300000);

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100 });
    document.getElementById('clear-stale-btn').click();

    assert.deepEqual(Object.keys(agents), ['["Codex","/home/user/project","here"]']);
    assert.equal(document.getElementById('agent-grid').children.length, 1);
});

test('clear stale keeps every card when none is stale', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100 });
    document.getElementById('clear-stale-btn').click();

    assert.equal(document.getElementById('agent-grid').children.length, 1);
});

test('typing in the search box hides the cards that do not match', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    listeners['agent-update']({ ...BASE, agent: 'Claude', session_id: 'two' });
    const search = document.getElementById('search-input');

    search.value = 'Claude';
    search.dispatchEvent(new window.Event('input'));

    assert.equal(agents['["Claude","/home/user/project","two"]'].style.display, 'flex');
    assert.equal(agents['["Codex","/home/user/project","one"]'].style.display, 'none');
});

test('an active search is re-applied to a card that arrives later', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    const search = document.getElementById('search-input');
    search.value = 'claude';
    search.dispatchEvent(new window.Event('input'));

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });

    assert.equal(agents['["Codex","/home/user/project","one"]'].style.display, 'none');
});

test('choosing a sort order rearranges the grid', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Gemini', session_id: 'one' });
    listeners['agent-update']({ ...BASE, agent: 'Claude', session_id: 'two' });
    const sort = document.getElementById('sort-select');

    choose(sort, 'name');
    sort.dispatchEvent(new window.Event('change'));

    assert.deepEqual(order(document), ['Claude', 'Gemini']);
});

test('a card arriving later is placed according to the chosen sort order', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    const sort = document.getElementById('sort-select');
    choose(sort, 'name');
    sort.dispatchEvent(new window.Event('change'));

    listeners['agent-update']({ ...BASE, agent: 'Gemini', session_id: 'one' });
    listeners['agent-update']({ ...BASE, agent: 'Claude', session_id: 'two' });

    assert.deepEqual(order(document), ['Claude', 'Gemini']);
});

test('the history icon opens the modal for that card', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    const key = '["Codex","/home/user/project","one"]';

    agents[key].querySelector('.history-icon').click();

    assert.ok(document.getElementById('history-modal').hasAttribute('open'));
    assert.equal(document.getElementById('modal-agent-name').textContent, `History: ${key}`);
    assert.equal(document.querySelectorAll('.history-item').length, 1);
});

test('the close button hides the modal and stops its live updates', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    const key = '["Codex","/home/user/project","one"]';
    agents[key].querySelector('.history-icon').click();

    document.querySelector('.close-btn').click();
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'grep' } });

    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
    assert.equal(document.querySelectorAll('.history-item').length, 1);
});

test('closing the modal returns focus to the history button that opened it', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    const history = agents['["Codex","/home/user/project","one"]'].querySelector('.history-icon');
    let focused = 0;
    history.focus = () => { focused++; };
    history.click();

    document.querySelector('.close-btn').click();

    assert.equal(focused, 1);
});

test('dismissing the modal with Escape stops its live updates', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    agents['["Codex","/home/user/project","one"]'].querySelector('.history-icon').click();

    // A dialog dismissed with Escape reports it as the close event.
    document.getElementById('history-modal').dispatchEvent(new window.Event('close'));
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'grep' } });

    assert.equal(document.querySelectorAll('.history-item').length, 1);
});

test('an open modal follows new events for the agent it is showing', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    agents['["Codex","/home/user/project","one"]'].querySelector('.history-icon').click();

    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'grep' } });

    assert.deepEqual(
        [...document.querySelectorAll('.history-details')].map((item) => item.textContent),
        ['Running: shell', 'Running: grep'],
    );
});

test('an open modal ignores events for a different agent', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    const key = '["Codex","/home/user/project","one"]';
    agents[key].querySelector('.history-icon').click();

    listeners['agent-update']({ ...BASE, session_id: 'two', details: { tool: 'grep' } });

    assert.equal(document.getElementById('modal-agent-name').textContent, `History: ${key}`);
    assert.deepEqual(
        [...document.querySelectorAll('.history-details')].map((item) => item.textContent),
        ['Running: shell'],
    );
});

test('clicking the backdrop closes the modal', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });
    agents['["Codex","/home/user/project","one"]'].querySelector('.history-icon').click();
    const modal = document.getElementById('history-modal');

    window.onclick({ target: modal });

    assert.ok(!modal.hasAttribute('open'));
});

test('clicking a card copies its workspace path', async (t) => {
    const { clipboard, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });

    agents['["Codex","/home/user/project","one"]'].click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(clipboard, ['/home/user/project']);
});

test('the menu icon opens the card options dialog', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });

    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();

    assert.ok(document.getElementById('card-menu-modal').hasAttribute('open'));
});

test('hiding a card removes it from view until its agent reports again', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });
    const card = agents['["Codex","/home/user/project","one"]'];
    card.querySelector('.menu-icon').click();

    document.getElementById('card-menu-hide').click();

    assert.equal(card.style.display, 'none');
    assert.equal(card.dataset.hidden, 'true');

    listeners['agent-update']({ ...BASE, session_id: 'one', details: { tool: 'shell' } });

    assert.equal(card.style.display, '');
    assert.equal(card.dataset.hidden, undefined);
});

test('the close button hides the card menu and returns focus to its opener', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });
    const menuButton = agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon');
    let focused = 0;
    menuButton.focus = () => { focused++; };
    menuButton.click();

    document.getElementById('card-menu-close').click();

    assert.ok(!document.getElementById('card-menu-modal').hasAttribute('open'));
    assert.equal(focused, 1);
});

test('clicking the card menu backdrop closes it', async (t) => {
    const { listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();
    const menu = document.getElementById('card-menu-modal');

    window.onclick({ target: menu });

    assert.ok(!menu.hasAttribute('open'));
});

test('adding an agent to the denylist reads the current list and appends to it', async (t) => {
    const saved = [];
    const { listeners } = await bootDashboard(t, {
        get_settings: async () => JSON.stringify({ agent_denylist: ['Gemini'] }),
        save_settings: async (payload) => {
            saved.push(JSON.parse(payload));
            return JSON.stringify({ ok: true });
        },
    });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();

    document.getElementById('card-menu-denylist').click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(saved, [{
        changes: { dashboard: { agent_denylist: ['Gemini', 'Codex'] } },
        update_hooks: false,
    }]);
});

test('a failed denylist save is reported instead of swallowed silently', async (t) => {
    const errors = [];
    const originalError = console.error;
    const { listeners } = await bootDashboard(t, {
        get_settings: async () => JSON.stringify({ agent_denylist: [] }),
        save_settings: async () => JSON.stringify({ ok: false, error: 'read-only' }),
    });
    console.error = (...args) => errors.push(args);
    t.after(() => { console.error = originalError; });

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();
    document.getElementById('card-menu-denylist').click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(errors, [['Failed to add agent to denylist:', 'read-only']]);
});

test('a malformed config error is reported instead of saving an incomplete denylist', async (t) => {
    const errors = [];
    const originalError = console.error;
    const saves = [];
    const { listeners } = await bootDashboard(t, {
        get_settings: async () => JSON.stringify({ error: 'invalid dashboard.json' }),
        save_settings: async (payload) => { saves.push(JSON.parse(payload)); return JSON.stringify({ ok: true }); },
    });
    console.error = (...args) => errors.push(args);
    t.after(() => { console.error = originalError; });

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();
    document.getElementById('card-menu-denylist').click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(errors, [['Failed to update agent denylist:', 'invalid dashboard.json']]);
    assert.deepEqual(saves, []);
});

test('a read-only denylist is not saved to from the card menu', async (t) => {
    const errors = [];
    const originalError = console.error;
    const saves = [];
    const { listeners } = await bootDashboard(t, {
        get_settings: async () => JSON.stringify({ agent_denylist: [], agent_denylist_editable: false }),
        save_settings: async (payload) => { saves.push(JSON.parse(payload)); return JSON.stringify({ ok: true }); },
    });
    console.error = (...args) => errors.push(args);
    t.after(() => { console.error = originalError; });

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();
    document.getElementById('card-menu-denylist').click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(saves, []);
    assert.equal(errors.length, 1);
});

test('adding an already-denylisted agent does not save again', async (t) => {
    let calls = 0;
    const { listeners } = await bootDashboard(t, {
        get_settings: async () => JSON.stringify({ agent_denylist: ['Codex'] }),
        save_settings: async () => { calls++; return JSON.stringify({ ok: true }); },
    });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();

    document.getElementById('card-menu-denylist').click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(calls, 0);
});

test('the card menu closes when its card is evicted to make room for a new one', async (t) => {
    const { listeners } = await bootDashboard(t, { get_max_active_agents: async () => 1 });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();
    assert.ok(document.getElementById('card-menu-modal').hasAttribute('open'));

    listeners['agent-update']({ ...BASE, agent: 'Claude', session_id: 'two' });

    assert.ok(!document.getElementById('card-menu-modal').hasAttribute('open'));
});

test('the card menu closes when its card is evicted by a lowered capacity', async (t) => {
    const { listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.menu-icon').click();
    assert.ok(document.getElementById('card-menu-modal').hasAttribute('open'));

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 0 });

    assert.ok(!document.getElementById('card-menu-modal').hasAttribute('open'));
});

test('a settings change carrying a denylist removes matching cards', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    listeners['agent-update']({ ...BASE, agent: 'Claude', session_id: 'two' });

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100, agent_denylist: ['Codex'] });

    assert.deepEqual(Object.keys(agents), ['["Claude","/home/user/project","two"]']);
    assert.equal(document.getElementById('agent-grid').children.length, 1);
});

test('denylisting the agent behind an open history modal closes it', async (t) => {
    const { listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents['["Codex","/home/user/project","one"]'].querySelector('.history-icon').click();

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100, agent_denylist: ['Codex'] });

    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
});
