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
        <dialog id="prompt-modal">
            <form id="prompt-form">
                <button type="button" id="prompt-close"></button>
                <div id="prompt-target"></div>
                <p id="prompt-warning"></p>
                <textarea id="prompt-text"></textarea>
                <p id="prompt-error"></p>
                <button type="button" id="prompt-cancel"></button>
                <button type="submit" id="prompt-send"></button>
            </form>
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
            get_ui_state: async () => '{}',
            save_ui_state: async () => true,
            notify: async () => true,
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
 * Checks a checkbox and fires its change event, the way clicking it would.
 * @param {HTMLInputElement} checkbox - The checkbox element.
 */
function check(checkbox) {
    checkbox.checked = true;
    checkbox.dispatchEvent(new window.Event('change'));
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

test('checking attention first ranks a waiting card above others regardless of the chosen sort', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Apple', session_id: 'one', state: 'Idle' });
    listeners['agent-update']({ ...BASE, agent: 'Zeta', session_id: 'two', state: 'Waiting for Input', details: { prompt: 'ok?' } });
    const sort = document.getElementById('sort-select');
    choose(sort, 'name');
    sort.dispatchEvent(new window.Event('change'));
    assert.deepEqual(order(document), ['Apple', 'Zeta']);

    check(document.getElementById('attention-first-toggle'));

    assert.deepEqual(order(document), ['Zeta', 'Apple']);
});

test('attention first re-sorts a card that arrives while it is checked', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    const sort = document.getElementById('sort-select');
    choose(sort, 'name');
    sort.dispatchEvent(new window.Event('change'));
    check(document.getElementById('attention-first-toggle'));

    listeners['agent-update']({ ...BASE, agent: 'Zeta', session_id: 'one', state: 'Waiting for Input', details: { prompt: 'ok?' } });
    listeners['agent-update']({ ...BASE, agent: 'Apple', session_id: 'two', state: 'Idle' });

    assert.deepEqual(order(document), ['Zeta', 'Apple']);
});

test('a card entering a waiting state sends a notification when notify is checked', async (t) => {
    const notified = [];
    const { document, listeners } = await bootDashboard(t, {
        notify: async (title, message) => { notified.push([title, message]); return true; },
    });
    check(document.getElementById('notify-toggle'));

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Waiting for Input', details: { prompt: 'continue?' } });

    assert.deepEqual(notified, [['Codex needs attention', 'Prompt: continue?']]);
});

test('no notification is sent while notify is unchecked', async (t) => {
    const notified = [];
    const { listeners } = await bootDashboard(t, {
        notify: async (title, message) => { notified.push([title, message]); return true; },
    });

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Waiting for Input', details: { prompt: 'continue?' } });

    assert.deepEqual(notified, []);
});

test('no notification is sent for an event that does not newly enter attention', async (t) => {
    const notified = [];
    const { document, listeners } = await bootDashboard(t, {
        notify: async (title, message) => { notified.push([title, message]); return true; },
    });
    check(document.getElementById('notify-toggle'));

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Waiting for Input', details: { prompt: 'continue?' } });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Input Required', details: { prompt: 'still?' } });

    assert.deepEqual(notified, [['Codex needs attention', 'Prompt: continue?']]);
});

test('the fleet summary shows zero totals immediately, before any telemetry arrives', async (t) => {
    const { document } = await bootDashboard(t);

    const texts = [...document.getElementById('fleet-summary').children].map((badge) => badge.textContent);
    assert.deepEqual(texts, ['0 agents', '0 need attention', '0 stale', '0 tokens']);
});

test('the fleet summary reflects arriving cards, attention state, and tokens', async (t) => {
    const { document, listeners } = await bootDashboard(t);

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Acting', details: { tool: 'shell', tokens: 1500 } });
    listeners['agent-update']({ ...BASE, agent: 'Claude', session_id: 'two', state: 'Error', details: { error: 'boom' } });

    const summary = document.getElementById('fleet-summary');
    const texts = [...summary.children].map((badge) => badge.textContent);
    assert.deepEqual(texts, ['2 agents', '1 needs attention', '0 stale', '1.5k tokens']);
});

test('clearing the dashboard resets the fleet summary', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });

    document.getElementById('clear-btn').click();

    const texts = [...document.getElementById('fleet-summary').children].map((badge) => badge.textContent);
    assert.deepEqual(texts, ['0 agents', '0 need attention', '0 stale', '0 tokens']);
});

const ONE = '["Codex","/home/user/project","one"]';

/**
 * Submits the prompt form the way pressing Send would, and lets the send finish.
 * @param {Document} document - The dashboard document.
 */
async function submitPrompt(document) {
    document.getElementById('prompt-form').dispatchEvent(new window.Event('submit', { cancelable: true }));
    await new Promise((resolve) => setImmediate(resolve));
}

test('the prompt button opens the dialog for its card', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });

    agents[ONE].querySelector('.prompt-icon').click();

    assert.ok(document.getElementById('prompt-modal').hasAttribute('open'));
    assert.equal(document.getElementById('prompt-target').textContent, 'Codex in /home/user/project');
});

test('sending a prompt posts the card identity and text, then closes the dialog', async (t) => {
    const requests = [];
    const { document, listeners } = await bootDashboard(t, {
        send_prompt: async (payload) => {
            requests.push(JSON.parse(payload));
            return JSON.stringify({ ok: true, id: 'id-1' });
        },
    });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();
    document.getElementById('prompt-text').value = 'run the tests';

    await submitPrompt(document);

    assert.deepEqual(requests, [{ agent: 'Codex', session_id: 'one', text: 'run the tests' }]);
    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
    assert.equal(document.getElementById('prompt-text').value, '');
    assert.equal(agents[ONE].querySelector('.prompt-status').textContent, 'Prompt sent, waiting for the relay…');
    assert.equal(document.getElementById('prompt-send').disabled, false);
});

test('a relay acknowledgment updates the card that sent the prompt', async (t) => {
    const { document, listeners } = await bootDashboard(t, {
        send_prompt: async () => JSON.stringify({ ok: true, id: 'id-ack' }),
    });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();
    document.getElementById('prompt-text').value = 'hello';
    await submitPrompt(document);

    listeners['prompt-ack']({ id: 'id-ack', status: 'delivered' });

    assert.equal(agents[ONE].querySelector('.prompt-status').textContent, 'Prompt delivered');
});

test('a rejected prompt keeps the dialog open with the reason and the text', async (t) => {
    const { document, listeners } = await bootDashboard(t, {
        send_prompt: async () => JSON.stringify({ ok: false, error: 'Not connected to the broker' }),
    });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();
    document.getElementById('prompt-text').value = 'keep me';

    await submitPrompt(document);

    assert.ok(document.getElementById('prompt-modal').hasAttribute('open'));
    assert.equal(document.getElementById('prompt-error').textContent, 'Not connected to the broker');
    assert.equal(document.getElementById('prompt-text').value, 'keep me');
    assert.equal(document.getElementById('prompt-send').disabled, false);
});

test('cancelling the prompt dialog sends nothing and returns focus to its button', async (t) => {
    let sent = 0;
    const { document, listeners } = await bootDashboard(t, {
        send_prompt: async () => { sent++; return JSON.stringify({ ok: true, id: 'x' }); },
    });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    const button = agents[ONE].querySelector('.prompt-icon');
    let focused = 0;
    button.focus = () => { focused++; };
    button.click();

    document.getElementById('prompt-cancel').click();

    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
    assert.equal(sent, 0);
    assert.equal(focused, 1);
});

test('the close button dismisses the prompt dialog', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();

    document.getElementById('prompt-close').click();

    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
});

test('the prompt dialog closes when its card is evicted by a smaller card limit', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 0 });

    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
});

test('the prompt dialog closes when its agent is denylisted', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();

    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100, agent_denylist: ['Codex'] });

    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
});

test('a new card arriving at capacity closes the prompt dialog of the evicted card', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 1 });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();

    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'two' });

    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
});

test('the prompt dialog warns when the agent is waiting for input', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Waiting for Input' });

    agents[ONE].querySelector('.prompt-icon').click();

    assert.match(document.getElementById('prompt-warning').textContent, /waiting for input/);
});

test('the prompt dialog shows no warning for an agent that is not waiting', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Waiting for Input' });
    agents[ONE].querySelector('.prompt-icon').click();
    document.getElementById('prompt-close').click();
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one', state: 'Idle' });

    agents[ONE].querySelector('.prompt-icon').click();

    assert.equal(document.getElementById('prompt-warning').textContent, '');
});

test('clearing the dashboard closes the prompt dialog of the removed card', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    agents[ONE].querySelector('.prompt-icon').click();

    document.getElementById('clear-btn').click();

    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
});

test('clearing stale cards closes the prompt dialog only when its card was removed', async (t) => {
    const { document, listeners } = await bootDashboard(t);
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'one' });
    listeners['agent-update']({ ...BASE, agent: 'Codex', session_id: 'two' });
    agents['["Codex","/home/user/project","two"]'].dataset.lastSeen = String(Date.now() - 300000);
    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100 });

    agents[ONE].querySelector('.prompt-icon').click();
    document.getElementById('clear-stale-btn').click();
    assert.ok(document.getElementById('prompt-modal').hasAttribute('open'));

    document.getElementById('prompt-close').click();
    agents[ONE].dataset.lastSeen = String(Date.now() - 300000);
    listeners['settings-changed']({ stale_threshold: 120, max_active_agents: 100 });
    agents[ONE].querySelector('.prompt-icon').click();
    document.getElementById('clear-stale-btn').click();
    assert.ok(!document.getElementById('prompt-modal').hasAttribute('open'));
});
