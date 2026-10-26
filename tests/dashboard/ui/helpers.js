// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

/**
 * @file helpers.js
 * @description Shared setup for the frontend tests that boot the whole dashboard.
 */

import { parseHTML } from 'linkedom';

import { clearAgents } from '../../../vauxhall/dashboard/ui/js/state.js';

export const PAGE = `
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
        <button id="install-hooks-btn"></button>
        <dialog id="install-dialog">
            <code id="install-path"></code>
            <fieldset id="install-agents"><legend>Agents</legend></fieldset>
            <p id="install-error"></p>
            <pre id="install-log"></pre>
            <p id="install-outcome"></p>
            <button type="button" id="install-run"></button>
            <button type="button" id="install-another"></button>
            <button type="button" id="install-close"></button>
        </dialog>
    </body></html>
`;

/**
 * Starts the dashboard against a fresh document and returns its test handles.
 * @param {import('node:test').TestContext} t - The test context, used to restore globals.
 * @param {object} [ipcOverrides] - Extra or replaced DashboardIPC bridge methods.
 * @param {object} [options] - Startup options.
 * @param {boolean} [options.pyloidLate] - Leave `window.pyloid` unset while
 *     the dashboard loads, so the test delivers it.
 * @returns {Promise<object>} The document, the captured backend callbacks, the
 *     window, the Pyloid object, and the scheduled interval callbacks.
 */
export async function bootDashboard(t, ipcOverrides = {}, { pyloidLate = false } = {}) {
    const { document, window } = parseHTML(PAGE);
    const listeners = {};
    const pyloid = {
        event: {
            listen(name, callback) {
                listeners[name] = callback;
            },
        },
    };
    if (!pyloidLate) window.pyloid = pyloid;
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
            get_saved_cards: async () => '[]',
            save_cards: async () => true,
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
    const intervals = [];
    globalThis.setInterval = (callback) => {
        intervals.push(callback);
        return 0;
    };
    globalThis.requestAnimationFrame = (callback) => {
        callback();
        return 0;
    };
    clearAgents();

    await import(`../../../vauxhall/dashboard/ui/app.js?boot=${Date.now()}${Math.random()}`);
    await new Promise((resolve) => setImmediate(resolve));

    return { document, clipboard, listeners, window, pyloid, intervals };
}

/**
 * Chooses an option in a select, the way clicking it would.
 * @param {HTMLSelectElement} select - The select element.
 * @param {string} value - The value of the option to choose.
 */
export function selectOption(select, value) {
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
export function cardOrder(document) {
    return [...document.getElementById('agent-grid').children].map(
        (card) => card.querySelector('.agent-name').textContent,
    );
}
