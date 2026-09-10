// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import {
    agentKey,
    agents,
    clearAgents,
} from '../../vauxhall/dashboard/ui/js/state.js';

test('agent identity includes session and cannot collide on delimiters', () => {
    const first = agentKey({ agent: 'A:B', workspace: 'C', session_id: 'D' });
    const second = agentKey({ agent: 'A', workspace: 'B:C', session_id: 'D' });
    const otherSession = agentKey({ agent: 'A:B', workspace: 'C', session_id: 'E' });

    assert.notEqual(first, second);
    assert.notEqual(first, otherSession);
    assert.equal(first, '["A:B","C","D"]');
});

test('same agent and workspace sessions create separate cards', async (t) => {
    const { document, window } = parseHTML(`
        <html><body>
            <div id="js-status"></div>
            <div id="agent-grid"></div>
            <div id="history-modal"></div>
        </body></html>
    `);
    let onAgentUpdate;
    window.pyloid = {
        event: {
            listen(name, callback) {
                if (name === 'agent-update') onAgentUpdate = callback;
            },
        },
    };
    window.ipc = {
        DashboardIPC: {
            ping: async () => false,
            copy_to_clipboard: async () => true,
        },
    };
    globalThis.document = document;
    globalThis.window = window;
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    const originalSetInterval = globalThis.setInterval;
    t.after(() => {
        globalThis.setInterval = originalSetInterval;
    });
    globalThis.setInterval = () => 0;
    clearAgents();

    await import(`../../vauxhall/dashboard/ui/app.js?test=${Date.now()}`);
    const base = {
        schema_version: 1,
        agent: 'Codex',
        workspace: '/workspace',
        state: 'Thinking',
        details: {},
    };
    onAgentUpdate({ ...base, session_id: 'native:one' });
    onAgentUpdate({ ...base, session_id: 'native:two' });
    const firstCard = agents['["Codex","/workspace","native:one"]'];
    const secondCard = agents['["Codex","/workspace","native:two"]'];

    onAgentUpdate({
        ...base,
        session_id: 'native:one',
        state: 'Acting',
        details: { tool: 'shell' },
    });

    assert.equal(document.getElementById('agent-grid').children.length, 2);
    assert.equal(Object.keys(agents).length, 2);
    assert.equal(firstCard.querySelector('.status-badge').textContent, 'Acting');
    assert.equal(firstCard.history.length, 2);
    assert.equal(firstCard.history[0].state, 'Acting');
    assert.equal(secondCard.querySelector('.status-badge').textContent, 'Thinking');
    assert.equal(secondCard.history.length, 1);
    assert.equal(secondCard.history[0].state, 'Thinking');
    assert.deepEqual(
        [...document.querySelectorAll('.agent-session')].map((element) => element.textContent),
        ['Session: native:one', 'Session: native:two'],
    );
});

test('configured capacity retains existing cards and closes an evicted card modal', async (t) => {
    const { document, window } = parseHTML(`
        <html><body>
            <div id="agent-grid"></div>
            <div id="history-modal"></div>
            <div id="modal-agent-name"></div>
            <input id="modal-search" value="">
            <select id="modal-state-filter"><option value="ALL" selected>All</option></select>
            <div id="modal-history-body"></div>
        </body></html>
    `);
    let onAgentUpdate;
    window.pyloid = {
        event: {
            listen(name, callback) {
                if (name === 'agent-update') onAgentUpdate = callback;
            },
        },
    };
    window.ipc = {
        DashboardIPC: {
            ping: async () => true,
            set_ready: async () => true,
            get_stale_threshold: async () => 120,
            get_max_active_agents: async () => 1,
            copy_to_clipboard: async () => true,
        },
    };
    globalThis.document = document;
    globalThis.window = window;
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    const originalSetInterval = globalThis.setInterval;
    t.after(() => {
        globalThis.setInterval = originalSetInterval;
    });
    globalThis.setInterval = () => 0;
    clearAgents();

    await import(`../../vauxhall/dashboard/ui/app.js?capacity=${Date.now()}`);
    await new Promise(resolve => setImmediate(resolve));

    const base = {
        schema_version: 1,
        agent: 'Codex',
        workspace: '/workspace',
        state: 'Thinking',
        details: {},
    };
    onAgentUpdate({ ...base, session_id: 'native:one' });
    const firstKey = '["Codex","/workspace","native:one"]';
    const firstCard = agents[firstKey];
    onAgentUpdate({ ...base, session_id: 'native:one', state: 'Acting' });

    assert.equal(document.getElementById('agent-grid').children.length, 1);
    assert.equal(firstCard.history.length, 2);

    firstCard.querySelector('.history-icon').click();
    assert.equal(document.getElementById('history-modal').style.display, 'block');

    onAgentUpdate({ ...base, session_id: 'native:two' });

    assert.equal(document.getElementById('agent-grid').children.length, 1);
    assert.equal(agents[firstKey], undefined);
    assert.equal(document.getElementById('history-modal').style.display, 'none');
});
