// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import {
    cachedTheme,
    cacheTheme,
    createPreferenceSaver,
    loadPreferences,
    restorePreferences,
} from '../../../vauxhall/dashboard/ui/js/preferences.js';

const flush = () => new Promise(resolve => setImmediate(resolve));

/**
 * Replaces localStorage for one test and returns its backing values.
 */
function withStorage(t, initial = {}) {
    const original = globalThis.localStorage;
    t.after(() => { globalThis.localStorage = original; });
    const values = { ...initial };
    globalThis.localStorage = {
        getItem: (key) => values[key] ?? null,
        setItem: (key, value) => { values[key] = String(value); },
        removeItem: (key) => { delete values[key]; },
    };
    return values;
}

function selects() {
    const { document } = parseHTML(`
        <html><body>
            <select id="sort-select">
                <option value="name" selected>Name</option>
                <option value="recent">Recent</option>
            </select>
            <select id="modal-state-filter">
                <option value="ALL" selected>All</option>
                <option value="Error">Error</option>
            </select>
        </body></html>
    `);
    return {
        sortSelect: document.getElementById('sort-select'),
        historyFilter: document.getElementById('modal-state-filter'),
    };
}

/**
 * Returns restorePreferences options that record what they apply and save.
 */
function view(overrides = {}) {
    const calls = { themes: [], sorts: [], saved: [] };
    return {
        calls,
        options: {
            cached: null,
            changed: new Set(),
            applyTheme: theme => calls.themes.push(theme),
            applySort: sort => calls.sorts.push(sort),
            save: changes => calls.saved.push(changes),
            ...selects(),
            ...overrides,
        },
    };
}

test('loads preferences and tolerates a missing or failing bridge', async (t) => {
    t.mock.method(console, 'error', () => {});

    assert.deepEqual(await loadPreferences(undefined), {});
    assert.deepEqual(await loadPreferences({}), {});
    assert.deepEqual(await loadPreferences({ get_ui_state: async () => '{"theme":"light"}' }), { theme: 'light' });
    assert.deepEqual(await loadPreferences({ get_ui_state: async () => 'null' }), {});
    assert.deepEqual(await loadPreferences({ get_ui_state: async () => '[]' }), {});
    assert.deepEqual(await loadPreferences({ get_ui_state: async () => { throw new Error('bridge'); } }), {});
});

test('saver batches changes and saves once after a pause', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const payloads = [];
    const { save } = createPreferenceSaver({ save_ui_state: async (payload) => payloads.push(JSON.parse(payload)) });

    save({ theme: 'light' });
    t.mock.timers.tick(300);
    save({ sort: 'recent' });
    t.mock.timers.tick(499);
    assert.deepEqual(payloads, []);

    t.mock.timers.tick(1);
    assert.deepEqual(payloads, [{ theme: 'light', sort: 'recent' }]);

    save({ theme: 'dark' });
    t.mock.timers.tick(500);
    assert.deepEqual(payloads, [{ theme: 'light', sort: 'recent' }, { theme: 'dark' }]);
});

test('flush sends queued changes immediately and only once', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const payloads = [];
    const saver = createPreferenceSaver({ save_ui_state: async (payload) => payloads.push(JSON.parse(payload)) });

    saver.flush();
    saver.save({ sort: 'recent' });
    saver.flush();
    t.mock.timers.tick(500);

    assert.deepEqual(payloads, [{ sort: 'recent' }]);
});

test('a save the bridge reports as failed is logged', async (t) => {
    const error = t.mock.method(console, 'error', () => {});
    const saver = createPreferenceSaver({ save_ui_state: async () => false });

    saver.save({ theme: 'light' });
    saver.flush();
    await flush();

    assert.equal(error.mock.callCount(), 1);
});

test('saver does nothing without a save bridge', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const saver = createPreferenceSaver({});

    saver.save({ theme: 'light' });
    saver.flush();
    t.mock.timers.tick(500);
});

test('theme cache tolerates unavailable storage', (t) => {
    const storage = withStorage(t, { 'vauxhall-theme': 'light' });
    assert.equal(cachedTheme(), 'light');
    cacheTheme('dark');
    assert.equal(storage['vauxhall-theme'], 'dark');

    globalThis.localStorage = {
        getItem: () => { throw new Error('denied'); },
        setItem: () => { throw new Error('denied'); },
    };
    assert.equal(cachedTheme(), null);
    cacheTheme('light');
});

test('restores theme, sort, and history filter', async () => {
    const { calls, options } = view();

    await restorePreferences(
        { get_ui_state: async () => '{"theme":"light","sort":"recent","history_filter":"Error"}' },
        options,
    );

    assert.deepEqual(calls.themes, ['light']);
    assert.deepEqual(calls.sorts, ['recent']);
    assert.equal(options.sortSelect.value, 'recent');
    assert.equal(options.historyFilter.value, 'Error');
    assert.deepEqual(calls.saved, []);
});

test('preferences changed before loading finished are not overwritten', async () => {
    const { calls, options } = view({ changed: new Set(['theme', 'sort', 'history_filter']) });

    await restorePreferences(
        { get_ui_state: async () => '{"theme":"light","sort":"recent","history_filter":"Error"}' },
        options,
    );

    assert.deepEqual(calls.themes, []);
    assert.deepEqual(calls.sorts, []);
    assert.equal(options.sortSelect.value, 'name');
    assert.equal(options.historyFilter.value, 'ALL');
});

test('ignores saved values the page does not offer', async () => {
    const { calls, options } = view();

    await restorePreferences(
        { get_ui_state: async () => '{"theme":"blue","sort":"missing","history_filter":"Idle"}' },
        options,
    );

    assert.deepEqual(calls.themes, []);
    assert.deepEqual(calls.sorts, []);
    assert.equal(options.sortSelect.value, 'name');
    assert.equal(options.historyFilter.value, 'ALL');
});

test('copies a theme cached by earlier versions into the state file', async () => {
    const { calls, options } = view({ cached: 'light' });

    await restorePreferences({ get_ui_state: async () => '{}' }, options);

    assert.deepEqual(calls.saved, [{ theme: 'light' }]);
});

test('a saved or already changed theme is not replaced by the cached theme', async () => {
    const saved = view({ cached: 'light' });
    await restorePreferences({ get_ui_state: async () => '{"theme":"dark"}' }, saved.options);
    assert.deepEqual(saved.calls.themes, ['dark']);
    assert.deepEqual(saved.calls.saved, []);

    const changed = view({ cached: 'light', changed: new Set(['theme']) });
    await restorePreferences({ get_ui_state: async () => '{}' }, changed.options);
    assert.deepEqual(changed.calls.saved, []);
});

function dashboardPage(t, ipc, storage = {}) {
    const { document, window } = parseHTML(`
        <html><body>
            <button id="theme-toggle"></button>
            <select id="sort-select">
                <option value="name" selected>Name</option>
                <option value="recent">Recent</option>
            </select>
            <div id="agent-grid"></div>
            <div id="history-modal"></div>
            <select id="modal-state-filter">
                <option value="ALL" selected>All</option>
                <option value="Error">Error</option>
            </select>
        </body></html>
    `);
    window.pyloid = { event: { listen() {} } };
    window.ipc = {
        DashboardIPC: {
            ping: async () => false,
            get_max_active_agents: async () => 100,
            ...ipc,
        },
    };
    const original = { document: globalThis.document, window: globalThis.window };
    t.after(() => Object.assign(globalThis, original));
    globalThis.document = document;
    globalThis.window = window;
    t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] });
    return { document, storage: withStorage(t, storage) };
}

test('dashboard restores preferences and saves changes through the bridge', async (t) => {
    const payloads = [];
    const { document, storage } = dashboardPage(t, {
        get_ui_state: async () => '{"theme":"light","sort":"recent"}',
        save_ui_state: async (payload) => payloads.push(JSON.parse(payload)),
    });

    await import(`../../../vauxhall/dashboard/ui/app.js?preferences=${Date.now()}`);
    await flush();
    await flush();

    assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
    assert.equal(storage['vauxhall-theme'], 'light');
    assert.equal(document.getElementById('sort-select').value, 'recent');

    document.getElementById('theme-toggle').click();
    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
    assert.equal(storage['vauxhall-theme'], 'dark');
    t.mock.timers.tick(500);

    assert.deepEqual(payloads, [{ theme: 'dark' }]);
});

test('dashboard paints the cached theme first and keeps a theme changed before loading', async (t) => {
    const payloads = [];
    let resolveState;
    const { document } = dashboardPage(
        t,
        {
            get_ui_state: () => new Promise(resolve => { resolveState = resolve; }),
            save_ui_state: async (payload) => payloads.push(JSON.parse(payload)),
        },
        { 'vauxhall-theme': 'light' },
    );

    await import(`../../../vauxhall/dashboard/ui/app.js?early-change=${Date.now()}`);
    assert.equal(document.documentElement.getAttribute('data-theme'), 'light');

    document.getElementById('theme-toggle').click();
    resolveState('{"theme":"light"}');
    await flush();
    await flush();

    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
    t.mock.timers.tick(500);
    assert.deepEqual(payloads, [{ theme: 'dark' }]);
});
