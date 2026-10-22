// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { agentKey, agents } from '../../../vauxhall/dashboard/ui/js/state.js';

import { bootDashboard } from './helpers.js';

test('agent identity includes session and cannot collide on delimiters', () => {
    const first = agentKey({ agent: 'A:B', workspace: 'C', session_id: 'D' });
    const second = agentKey({ agent: 'A', workspace: 'B:C', session_id: 'D' });
    const otherSession = agentKey({ agent: 'A:B', workspace: 'C', session_id: 'E' });

    assert.notEqual(first, second);
    assert.notEqual(first, otherSession);
    assert.equal(first, '["A:B","C","D"]');
});

test('same agent and workspace sessions create separate cards', async (t) => {
    const { document, listeners } = await bootDashboard(t, { ping: async () => false });
    const onAgentUpdate = listeners['agent-update'];
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
    // The page sorts by recency, so compare the sessions shown, not their order.
    assert.deepEqual(
        [...document.querySelectorAll('.agent-session')].map((element) => element.textContent).sort(),
        ['Session: native:one', 'Session: native:two'],
    );
});

test('configured capacity retains existing cards and closes an evicted card modal', async (t) => {
    const { document, listeners } = await bootDashboard(t, { get_max_active_agents: async () => 1 });
    const onAgentUpdate = listeners['agent-update'];

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

    const opener = firstCard.querySelector('.history-icon');
    opener.click();
    assert.ok(document.getElementById('history-modal').hasAttribute('open'));
    const focused = [];
    opener.focus = () => focused.push('opener');
    document.getElementById('agent-grid').focus = () => focused.push('grid');

    onAgentUpdate({ ...base, session_id: 'native:two' });

    assert.equal(document.getElementById('agent-grid').children.length, 1);
    assert.equal(agents[firstKey], undefined);
    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
    // The opener left with its card, so focus goes to the grid, not the body.
    assert.deepEqual(focused, ['grid']);
});

test('capacity loads before readiness delivers queued events', async (t) => {
    let listeners;
    let resolveMaximum;
    let setReadyCalls = 0;
    const maximum = new Promise(resolve => {
        resolveMaximum = resolve;
    });
    const base = {
        schema_version: 1,
        agent: 'Codex',
        workspace: '/workspace',
        state: 'Thinking',
        details: {},
    };
    const booted = await bootDashboard(t, {
        set_ready: async () => {
            setReadyCalls += 1;
            listeners['agent-update']({ ...base, session_id: 'queued:one' });
            listeners['agent-update']({ ...base, session_id: 'queued:two' });
            return true;
        },
        get_max_active_agents: () => maximum,
    });
    ({ listeners } = booted);
    const { document } = booted;

    assert.equal(setReadyCalls, 0);

    resolveMaximum(1);
    await new Promise(resolve => setImmediate(resolve));

    assert.equal(setReadyCalls, 1);
    assert.equal(document.getElementById('agent-grid').children.length, 1);
    assert.equal(Object.keys(agents).length, 1);
});
