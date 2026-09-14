// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { Event as DOMEvent, parseHTML } from 'linkedom';

import {
    collectChanges,
    initSettings,
    renderSettingsForm,
    savedNotes,
    showErrors,
} from '../../../vauxhall/dashboard/ui/js/settings.js';

const DIALOG = `
    <button id="settings-btn"></button>
    <dialog id="settings-dialog">
        <form id="settings-form">
            <p id="settings-message"></p>
            <div id="settings-fields"></div>
            <div id="settings-hooks" hidden>
                <input type="checkbox" id="settings-update-hooks">
                <code id="settings-hooks-path"></code>
            </div>
            <button type="button" id="settings-cancel"></button>
        </form>
    </dialog>
`;

function field(overrides = {}) {
    return {
        key: 'mqtt.port',
        section: 'mqtt',
        name: 'port',
        value: 1883,
        default: 1883,
        type: 'integer',
        min: 1,
        max: 65535,
        choices: null,
        required: false,
        source: 'default',
        location: null,
        editable: true,
        apply: 'reconnect',
        ...overrides,
    };
}

function descriptor() {
    return {
        fields: [
            field({
                key: 'mqtt.host', name: 'host', value: 'localhost', default: 'localhost',
                type: 'string', min: null, max: null, required: true,
                source: 'environment', location: '<img src=x onerror=alert(1)>', editable: false,
            }),
            field(),
            field({
                key: 'logging.level', section: 'logging', name: 'level', value: 'INFO', default: 'INFO',
                type: 'string', min: null, max: null, choices: ['CRITICAL', 'DEBUG', 'ERROR', 'INFO', 'WARNING'],
                apply: 'live',
            }),
            field({
                key: 'dashboard.debug', section: 'dashboard', name: 'debug', value: false, default: false,
                type: 'boolean', min: null, max: null, source: 'file', location: '/home/u/.config/vauxhall/vauxhall_dashboard.json',
                apply: 'restart',
            }),
        ],
        paths: {
            dashboard: '/home/u/.config/vauxhall/vauxhall_dashboard.json',
            hooks: '/home/u/.config/vauxhall/vauxhall_hooks.json',
        },
        hooks_error: null,
    };
}

// linkedom elements only dispatch linkedom's own Event, which settings.js
// creates through the global Event constructor.
const NodeEvent = globalThis.Event;
after(() => {
    globalThis.Event = NodeEvent;
});

function setup(body = '<div id="fields"></div>') {
    const { document, window } = parseHTML(`<html><body>${body}</body></html>`);
    globalThis.document = document;
    globalThis.window = window;
    globalThis.Event = DOMEvent;
    return document;
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0));

function setInput(document, id, value) {
    const input = document.getElementById(id);
    if (typeof value === 'boolean') input.checked = value;
    else if (input.tagName === 'SELECT') [...input.options].find(option => option.value === value).selected = true;
    else input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
}

test('renders sections, input types, and read-only fields as text', () => {
    const document = setup();
    const container = document.getElementById('fields');

    renderSettingsForm(container, descriptor());

    const legends = [...container.querySelectorAll('legend')].map(legend => legend.textContent);
    assert.deepEqual(legends, ['MQTT', 'Logging', 'Dashboard']);

    const host = document.getElementById('setting-mqtt-host');
    assert.equal(host.getAttribute('type'), 'text');
    assert.ok(host.hasAttribute('disabled'));
    const hostRow = host.parentElement;
    assert.equal(hostRow.querySelector('.settings-note').textContent, 'Set by <img src=x onerror=alert(1)>.');
    assert.equal(container.querySelector('img'), null);
    assert.ok(hostRow.querySelector('.settings-reset').hasAttribute('disabled'));

    const port = document.getElementById('setting-mqtt-port');
    assert.equal(port.getAttribute('type'), 'number');
    assert.equal(port.getAttribute('min'), '1');
    assert.equal(port.value, '1883');
    assert.equal(port.hasAttribute('disabled'), false);

    assert.equal(document.getElementById('setting-logging-level').tagName, 'SELECT');
    assert.equal(document.getElementById('setting-dashboard-debug').getAttribute('type'), 'checkbox');
    assert.equal(document.querySelector('label[for="setting-mqtt-port"]').textContent, 'port');
});

test('collects only changed editable values with their types', () => {
    const document = setup();
    const container = document.getElementById('fields');
    const settings = descriptor();
    renderSettingsForm(container, settings);

    assert.deepEqual(collectChanges(container, settings), { changes: {}, errors: {} });

    setInput(document, 'setting-mqtt-port', '1884');
    setInput(document, 'setting-logging-level', 'DEBUG');
    setInput(document, 'setting-dashboard-debug', true);
    setInput(document, 'setting-mqtt-host', 'ignored');

    assert.deepEqual(collectChanges(container, settings), {
        changes: { mqtt: { port: 1884 }, logging: { level: 'DEBUG' }, dashboard: { debug: true } },
        errors: {},
    });
});

test('reports and clears client-side errors', () => {
    const document = setup();
    const container = document.getElementById('fields');
    const settings = descriptor();
    renderSettingsForm(container, settings);

    for (const value of ['0', '1.5', '', 'abc']) {
        setInput(document, 'setting-mqtt-port', value);
        const { changes, errors } = collectChanges(container, settings);
        assert.deepEqual(changes, {});
        assert.ok(errors['mqtt.port'], `expected an error for ${JSON.stringify(value)}`);
    }

    const { errors } = collectChanges(container, settings);
    showErrors(container, errors);
    const port = document.getElementById('setting-mqtt-port');
    assert.equal(port.getAttribute('aria-invalid'), 'true');
    assert.equal(document.getElementById('setting-mqtt-port-error').textContent, 'Enter a whole number.');

    showErrors(container, {});
    assert.equal(port.hasAttribute('aria-invalid'), false);
    assert.equal(document.getElementById('setting-mqtt-port-error').textContent, '');
});

test('reset restores the default value', () => {
    const document = setup();
    const container = document.getElementById('fields');
    const settings = descriptor();
    renderSettingsForm(container, settings);

    setInput(document, 'setting-mqtt-port', '2000');
    document.getElementById('setting-mqtt-port').parentElement.querySelector('.settings-reset')
        .dispatchEvent(new Event('click'));

    assert.equal(document.getElementById('setting-mqtt-port').value, '1883');
});

test('saved notes mention restarts and hook failures only', () => {
    assert.equal(savedNotes({ ok: true, restart_required: [], hooks_error: null }), '');
    assert.equal(
        savedNotes({ ok: true, restart_required: ['dashboard.port'], hooks_error: 'read-only' }),
        'Saved. Restart Vauxhall to apply: dashboard.port. Hooks configuration not updated: read-only',
    );
});

test('dialog saves changes, offers hooks updates, and shows server errors', async () => {
    const document = setup(DIALOG);
    const requests = [];
    const responses = [
        { ok: false, error: 'Invalid configuration value for mqtt.port', field: 'mqtt.port', file: 'dashboard' },
        { ok: true, restart_required: [], reconnecting: true, hooks_updated: true, hooks_error: null },
    ];
    initSettings({
        get_settings: async () => JSON.stringify(descriptor()),
        save_settings: async (payload) => {
            requests.push(JSON.parse(payload));
            return JSON.stringify(responses.shift());
        },
    });
    const dialog = document.getElementById('settings-dialog');
    const hooks = document.getElementById('settings-hooks');
    const form = document.getElementById('settings-form');

    document.getElementById('settings-btn').dispatchEvent(new Event('click'));
    await flush();
    assert.ok(dialog.hasAttribute('open'));
    assert.ok(hooks.hasAttribute('hidden'));
    assert.equal(document.getElementById('settings-hooks-path').textContent, descriptor().paths.hooks);

    setInput(document, 'setting-mqtt-port', '1884');
    assert.equal(hooks.hasAttribute('hidden'), false);
    document.getElementById('settings-update-hooks').checked = true;

    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    assert.deepEqual(requests[0], { changes: { mqtt: { port: 1884 } }, update_hooks: true });
    assert.ok(dialog.hasAttribute('open'));
    assert.equal(document.getElementById('setting-mqtt-port-error').textContent, 'Invalid configuration value for mqtt.port');
    assert.match(document.getElementById('settings-message').textContent, /^Nothing saved\./);

    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    assert.equal(requests.length, 2);
    assert.equal(dialog.hasAttribute('open'), false);
});

test('dialog blocks invalid input and closes without saving when unchanged', async () => {
    const document = setup(DIALOG);
    const requests = [];
    initSettings({
        get_settings: async () => JSON.stringify(descriptor()),
        save_settings: async (payload) => {
            requests.push(payload);
            return '{"ok": true}';
        },
    });
    const dialog = document.getElementById('settings-dialog');
    const form = document.getElementById('settings-form');

    document.getElementById('settings-btn').dispatchEvent(new Event('click'));
    await flush();
    setInput(document, 'setting-mqtt-port', '0');
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    assert.equal(requests.length, 0);
    assert.equal(document.getElementById('settings-message').textContent, 'Fix the highlighted settings.');

    setInput(document, 'setting-mqtt-port', '1883');
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    assert.equal(requests.length, 0);
    assert.equal(dialog.hasAttribute('open'), false);
});

test('dialog shows a load error instead of fields', async () => {
    const document = setup(DIALOG);
    initSettings({
        get_settings: async () => JSON.stringify({ error: '/x: mqtt must be an object, got 5' }),
        save_settings: async () => '{}',
    });

    document.getElementById('settings-btn').dispatchEvent(new Event('click'));
    await flush();

    assert.equal(document.getElementById('settings-message').textContent, '/x: mqtt must be an object, got 5');
    assert.equal(document.getElementById('settings-fields').children.length, 0);
});
