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

test('same agent and workspace sessions create separate cards', async () => {
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

    assert.equal(document.getElementById('agent-grid').children.length, 2);
    assert.equal(Object.keys(agents).length, 2);
    assert.deepEqual(
        [...document.querySelectorAll('.agent-session')].map((element) => element.textContent),
        ['Session: native:one', 'Session: native:two'],
    );
});
