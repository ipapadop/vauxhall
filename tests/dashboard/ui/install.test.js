// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Event as DOMEvent, parseHTML } from 'linkedom';

import { agentStatus, defaultChecked, initInstall } from '../../../vauxhall/dashboard/ui/js/install.js';

const INSTALL_DIALOG = `
    <p id="js-status"></p>
    <button id="install-hooks-btn" aria-haspopup="dialog">Install Hooks…</button>
    <dialog id="install-dialog" aria-labelledby="install-title">
        <h2 id="install-title">Install Hooks</h2>
        <code id="install-path"></code>
        <fieldset id="install-agents"><legend>Agents</legend></fieldset>
        <p id="install-error" role="alert"></p>
        <pre id="install-log" role="log" aria-live="polite"></pre>
        <p id="install-outcome" role="status"></p>
        <button type="button" id="install-run">Install</button>
        <button type="button" id="install-another">Choose another directory…</button>
        <button type="button" id="install-close">Close</button>
    </dialog>
`;

const flush = () => new Promise(resolve => setTimeout(resolve, 0));

function agent(key, overrides = {}) {
    const names = { claude: 'Claude Code', codex: 'Codex', gemini: 'Gemini' };
    return { agent: key, name: names[key], detected: false, installed: false, error: null, ...overrides };
}

const DETECTED = [
    agent('claude', { detected: true }),
    agent('codex', { detected: true, installed: true }),
    agent('gemini'),
];

// linkedom elements only dispatch linkedom's own Event.
function setup(t) {
    const { document, window } = parseHTML(`<html><body>${INSTALL_DIALOG}</body></html>`);
    const saved = { document: globalThis.document, window: globalThis.window, Event: globalThis.Event };
    globalThis.document = document;
    globalThis.window = window;
    globalThis.Event = DOMEvent;
    t.after(() => Object.assign(globalThis, saved));
    return document;
}

/**
 * Builds a fake bridge whose replies are scripted per method.
 * @param {object} replies - Method name to a list of reply objects, or one reply for every call.
 * @returns {object} The bridge, with `calls` recording each call's arguments.
 */
function fakeIpc(replies) {
    const calls = { select_install_directory: [], install_hooks: [], detect_agents: [] };
    const ipc = { calls };
    for (const name of Object.keys(calls)) {
        ipc[name] = async (...args) => {
            calls[name].push(args);
            const reply = replies[name];
            return JSON.stringify(Array.isArray(reply) ? reply.shift() : reply);
        };
    }
    return ipc;
}

async function openWith(t, replies) {
    const document = setup(t);
    const ipc = fakeIpc({
        select_install_directory: { ok: true, path: '/work/a', agents: DETECTED },
        install_hooks: { ok: true },
        detect_agents: { ok: true, agents: DETECTED },
        ...replies,
    });
    const handlers = initInstall(ipc);
    document.getElementById('install-hooks-btn').dispatchEvent(new Event('click'));
    await flush();
    return { document, ipc, handlers, $: (id) => document.getElementById(id) };
}

function checkbox(document, key) {
    return document.getElementById(`install-agent-${key}`);
}

function tick(document, key, checked = true) {
    const box = checkbox(document, key);
    box.checked = checked;
    box.dispatchEvent(new Event('change', { bubbles: true }));
}

test('defaultChecked ticks only agents detected without hooks or errors', () => {
    assert.equal(defaultChecked(agent('claude', { detected: true })), true);
    assert.equal(defaultChecked(agent('claude', { detected: true, installed: true })), false);
    assert.equal(defaultChecked(agent('claude')), false);
    assert.equal(defaultChecked(agent('claude', { detected: true, error: 'bad' })), false);
});

test('agentStatus names each agent state', () => {
    assert.equal(agentStatus(agent('claude', { detected: true })), 'Detected');
    assert.equal(agentStatus(agent('claude', { detected: true, installed: true })), 'Hooks installed — Reinstall');
    assert.equal(agentStatus(agent('claude')), 'Not detected');
    assert.equal(agentStatus(agent('claude', { detected: true, error: 'Bad JSON' })), 'Bad JSON');
});

test('initInstall does nothing without the bridge or its markup', (t) => {
    setup(t);
    assert.equal(initInstall(undefined), null);
    document.getElementById('install-dialog').remove();
    assert.equal(initInstall(fakeIpc({})), null);
});

test('toolbar click opens the dialog with the agent list', async (t) => {
    const { document, $ } = await openWith(t);

    assert.ok($('install-dialog').hasAttribute('open'));
    assert.equal($('install-path').textContent, '/work/a');
    const labels = [...document.querySelectorAll('#install-agents label')].map(label => label.textContent);
    assert.deepEqual(labels, ['Claude Code — Detected', 'Codex — Hooks installed — Reinstall', 'Gemini — Not detected']);
    assert.deepEqual(['claude', 'codex', 'gemini'].map(key => checkbox(document, key).checked), [true, false, false]);
    assert.equal($('install-agents').querySelector('legend').textContent, 'Agents');
});

test('cancelled picker leaves the dialog closed', async (t) => {
    const { $ } = await openWith(t, { select_install_directory: { ok: false } });

    assert.equal($('install-dialog').hasAttribute('open'), false);
    assert.equal($('js-status').textContent, '');
});

test('a picker error is shown in the status line', async (t) => {
    const { $ } = await openWith(t, { select_install_directory: { ok: false, error: 'Could not choose a directory' } });

    assert.equal($('install-dialog').hasAttribute('open'), false);
    assert.equal($('js-status').textContent, 'Could not choose a directory');
});

test('Install is disabled until an agent is ticked', async (t) => {
    const { document, $ } = await openWith(t);

    tick(document, 'claude', false);
    assert.equal($('install-run').disabled, true);
    tick(document, 'gemini');
    assert.equal($('install-run').disabled, false);
});

test('Install sends the path and ticked agents', async (t) => {
    const { document, ipc, $ } = await openWith(t);
    tick(document, 'codex');

    $('install-run').dispatchEvent(new Event('click'));
    await flush();

    assert.deepEqual(ipc.calls.install_hooks.map(([payload]) => JSON.parse(payload)), [
        { path: '/work/a', agents: ['claude', 'codex'] },
    ]);
    assert.equal($('install-outcome').textContent, 'Installing…');
});

test('running disables every control and blocks Escape', async (t) => {
    const { document, $ } = await openWith(t);
    $('install-run').dispatchEvent(new Event('click'));
    await flush();

    for (const id of ['install-run', 'install-another', 'install-close']) assert.equal($(id).disabled, true, id);
    for (const key of ['claude', 'codex', 'gemini']) assert.equal(checkbox(document, key).disabled, true, key);
    const cancel = new Event('cancel', { cancelable: true });
    $('install-dialog').dispatchEvent(cancel);
    assert.equal(cancel.defaultPrevented, true);
    assert.ok($('install-dialog').hasAttribute('open'));
});

test('Escape closes the dialog when no install runs', async (t) => {
    const { $ } = await openWith(t);
    const cancel = new Event('cancel', { cancelable: true });

    $('install-dialog').dispatchEvent(cancel);

    assert.equal(cancel.defaultPrevented, false);
});

test('output lines append to the log as text', async (t) => {
    const { handlers, $ } = await openWith(t);

    handlers.onOutput({ line: 'Creating virtual environment...' });
    handlers.onOutput({ line: '<b>not markup</b>' });

    assert.equal($('install-log').textContent, 'Creating virtual environment...\n<b>not markup</b>\n');
    assert.equal($('install-log').querySelector('b'), null);
});

test('the log follows new lines only when scrolled to the bottom', async (t) => {
    const { handlers, $ } = await openWith(t);
    const log = $('install-log');
    Object.defineProperty(log, 'clientHeight', { value: 100 });
    Object.defineProperty(log, 'scrollHeight', { value: 500, configurable: true });

    log.scrollTop = 400;
    handlers.onOutput({ line: 'a' });
    assert.equal(log.scrollTop, 500);

    log.scrollTop = 0;
    handlers.onOutput({ line: 'b' });
    assert.equal(log.scrollTop, 0);
});

test('done shows the outcome, re-detects, and focuses Close', async (t) => {
    const after = [agent('claude', { detected: true, installed: true }), agent('codex'), agent('gemini')];
    const { document, ipc, handlers, $ } = await openWith(t, { detect_agents: { ok: true, agents: after } });
    let focused = null;
    $('install-close').focus = () => { focused = 'install-close'; };
    $('install-run').dispatchEvent(new Event('click'));
    await flush();

    await handlers.onDone({ ok: true, returncode: 0 });

    assert.equal($('install-outcome').textContent, 'Hooks installed.');
    assert.deepEqual(ipc.calls.detect_agents, [['/work/a']]);
    assert.equal(document.querySelector('label[for="install-agent-claude"]').textContent, 'Claude Code — Hooks installed — Reinstall');
    for (const id of ['install-another', 'install-close']) assert.equal($(id).disabled, false, id);
    assert.equal(focused, 'install-close');
});

test('a failed exit shows the exit code', async (t) => {
    const { handlers, $ } = await openWith(t);
    $('install-run').dispatchEvent(new Event('click'));
    await flush();

    await handlers.onDone({ ok: false, returncode: 1 });
    assert.equal($('install-outcome').textContent, 'Install failed (exit 1). See the log above.');

    await handlers.onDone({ ok: false, returncode: null });
    assert.equal($('install-outcome').textContent, 'Install failed. See the log above.');
});

test('a rejected install shows the error and keeps controls enabled', async (t) => {
    const { $ } = await openWith(t, { install_hooks: { ok: false, error: 'An install is already running' } });

    $('install-run').dispatchEvent(new Event('click'));
    await flush();

    assert.equal($('install-error').textContent, 'An install is already running');
    assert.equal($('install-outcome').textContent, '');
    assert.equal($('install-run').disabled, false);
    assert.equal($('install-close').disabled, false);
});

test('choose another directory clears the log and rebuilds the list', async (t) => {
    const { document, handlers, $ } = await openWith(t, {
        select_install_directory: [
            { ok: true, path: '/work/a', agents: DETECTED },
            { ok: true, path: '/work/b', agents: [agent('claude'), agent('codex'), agent('gemini', { detected: true })] },
        ],
    });
    $('install-run').dispatchEvent(new Event('click'));
    await flush();
    handlers.onOutput({ line: 'old' });
    await handlers.onDone({ ok: true, returncode: 0 });

    $('install-another').dispatchEvent(new Event('click'));
    await flush();

    assert.equal($('install-path').textContent, '/work/b');
    assert.equal($('install-log').textContent, '');
    assert.equal($('install-outcome').textContent, '');
    assert.deepEqual(['claude', 'codex', 'gemini'].map(key => checkbox(document, key).checked), [false, false, true]);
});

test('cancelling another directory keeps the current one', async (t) => {
    const { $ } = await openWith(t, {
        select_install_directory: [{ ok: true, path: '/work/a', agents: DETECTED }, { ok: false }],
    });

    $('install-another').dispatchEvent(new Event('click'));
    await flush();

    assert.equal($('install-path').textContent, '/work/a');
    assert.ok($('install-dialog').hasAttribute('open'));
});

test('done while the dialog is closed does not throw and leaves it unlocked', async (t) => {
    const { handlers, $ } = await openWith(t);
    $('install-close').dispatchEvent(new Event('click'));
    assert.equal($('install-dialog').hasAttribute('open'), false);

    await handlers.onDone({ ok: true, returncode: 0 });
    $('install-hooks-btn').dispatchEvent(new Event('click'));
    await flush();

    assert.ok($('install-dialog').hasAttribute('open'));
    assert.equal($('install-close').disabled, false);
    assert.equal($('install-outcome').textContent, '');
});

test('closing returns focus to the toolbar button', async (t) => {
    const { $ } = await openWith(t);
    let focused = null;
    $('install-hooks-btn').focus = () => { focused = 'install-hooks-btn'; };

    $('install-close').dispatchEvent(new Event('click'));

    assert.equal(focused, 'install-hooks-btn');
});

test('a dialog closed during an install opens again', async (t) => {
    const { $ } = await openWith(t);
    $('install-run').dispatchEvent(new Event('click'));
    await flush();

    // Chromium may let a repeated Escape close it despite preventDefault.
    $('install-dialog').removeAttribute('open');
    $('install-dialog').dispatchEvent(new Event('close'));

    assert.ok($('install-dialog').hasAttribute('open'));
});

test('the toolbar button returns to a running install without the picker', async (t) => {
    const { ipc, handlers, $ } = await openWith(t);
    $('install-run').dispatchEvent(new Event('click'));
    await flush();
    handlers.onOutput({ line: 'Creating virtual environment...' });
    $('install-dialog').removeAttribute('open');

    $('install-hooks-btn').dispatchEvent(new Event('click'));
    await flush();

    assert.equal(ipc.calls.select_install_directory.length, 1);
    assert.ok($('install-dialog').hasAttribute('open'));
    assert.equal($('install-path').textContent, '/work/a');
    assert.equal($('install-log').textContent, 'Creating virtual environment...\n');
});
