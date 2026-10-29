// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { agentKey, agents, cardIdentity } from '../../../vauxhall/dashboard/ui/js/state.js';

import { bootDashboard } from './helpers.js';

test('agent identity is agent and session, ignores workspace, and cannot collide on delimiters', () => {
    const first = agentKey({ agent: 'A:B', workspace: 'C', session_id: 'D' });
    const second = agentKey({ agent: 'A', session_id: 'B:D' });
    const otherSession = agentKey({ agent: 'A:B', workspace: 'C', session_id: 'E' });
    const otherWorkspace = agentKey({ agent: 'A:B', workspace: 'C/sub', session_id: 'D' });

    assert.notEqual(first, second);
    assert.notEqual(first, otherSession);
    assert.equal(first, otherWorkspace);
    assert.equal(first, '["A:B","D"]');
});

test('a session that changes directory keeps one card showing the latest workspace', async (t) => {
    const { document, listeners } = await bootDashboard(t, { ping: async () => false });
    const base = { schema_version: 1, agent: 'Codex', session_id: 'native:one', details: {} };

    listeners['agent-update']({ ...base, workspace: '/home/user/project', state: 'Thinking' });
    listeners['agent-update']({ ...base, workspace: 'C:\\remote-ish', env: 'remote', state: 'Acting' });

    assert.equal(document.getElementById('agent-grid').children.length, 1);
    const card = agents['["Codex","native:one"]'];
    assert.equal(card.history.length, 2);
    assert.deepEqual(cardIdentity(card), { agent: 'Codex', workspace: 'C:\\remote-ish', session_id: 'native:one' });
    const badge = card.querySelector('.env-badge');
    assert.equal(badge.textContent, 'remote');
    assert.deepEqual([...badge.classList].filter((name) => name.startsWith('env-') && name !== 'env-badge'), ['env-remote']);
    assert.equal(
        card.querySelector('.agent-workspace').getAttribute('aria-label'),
        'Open activity for Codex in C:\\remote-ish, session native:one',
    );
    assert.equal(
        card.querySelector('.menu-icon').getAttribute('aria-label'),
        'Options for Codex in C:\\remote-ish, session native:one',
    );
});

test('a cleared session removes its card and saves the remaining cards', async (t) => {
    const saves = [];
    const { document, listeners } = await bootDashboard(t, {
        ping: async () => false,
        save_cards: async (json) => {
            saves.push(JSON.parse(json));
            return true;
        },
    });
    const base = { schema_version: 1, agent: 'Claude Code', workspace: '/home/user/project' };
    listeners['agent-update']({ ...base, session_id: 'old', state: 'Thinking', details: {} });
    listeners['agent-update']({ ...base, session_id: 'new', state: 'Thinking', details: {} });

    const card = agents['["Claude Code","old"]'];
    const opener = card.querySelector('.agent-workspace');
    opener.click();
    const focused = [];
    document.getElementById('agent-grid').focus = () => focused.push('grid');

    listeners['agent-update']({
        ...base, session_id: 'old', state: 'Idle', details: { status: 'session cleared', end_reason: 'clear' },
    });

    assert.equal(agents['["Claude Code","old"]'], undefined);
    assert.ok(!card.isConnected);
    assert.equal(document.getElementById('agent-grid').children.length, 1);
    assert.ok(!document.getElementById('history-modal').hasAttribute('open'));
    assert.deepEqual(focused, ['grid']);
    assert.match(document.getElementById('fleet-summary').textContent, /\b1\b/);

    // An end for a session without a card doesn't create one.
    listeners['agent-update']({
        ...base, session_id: 'unseen', state: 'Idle', details: { end_reason: 'clear' },
    });
    assert.equal(document.getElementById('agent-grid').children.length, 1);

    // The 500 ms debounce isn't waited for: pagehide flushes the save.
    document.defaultView.dispatchEvent(new document.defaultView.Event('pagehide'));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(saves.at(-1).map((entry) => entry.session_id), ['new']);
});

test('another session end keeps its card', async (t) => {
    const { listeners } = await bootDashboard(t, { ping: async () => false });
    const base = { schema_version: 1, agent: 'Claude Code', workspace: '/home/user/project', session_id: 'one' };
    listeners['agent-update']({ ...base, state: 'Thinking', details: {} });

    listeners['agent-update']({ ...base, state: 'Idle', details: { status: 'logged out', end_reason: 'logout' } });

    assert.equal(agents['["Claude Code","one"]'].dataset.state, 'Idle');
});

test('a card reports the identity it was built from', async (t) => {
    const { listeners } = await bootDashboard(t, { ping: async () => false });
    const identity = { agent: 'Codex', workspace: '/workspace', session_id: 'native:one' };

    listeners['agent-update']({ schema_version: 1, ...identity, state: 'Idle', details: {} });

    assert.deepEqual(cardIdentity(agents[agentKey(identity)]), identity);
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
    const firstCard = agents['["Codex","native:one"]'];
    const secondCard = agents['["Codex","native:two"]'];

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
    const firstKey = '["Codex","native:one"]';
    const firstCard = agents[firstKey];
    onAgentUpdate({ ...base, session_id: 'native:one', state: 'Acting' });

    assert.equal(document.getElementById('agent-grid').children.length, 1);
    assert.equal(firstCard.history.length, 2);

    const opener = firstCard.querySelector('.agent-workspace');
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
