// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';

import { parseHTML } from 'linkedom';

import {
    agents,
    clearAgents,
    ensureAgentCapacity,
    evictAgents,
} from '../../../vauxhall/dashboard/ui/js/state.js';

let document;

beforeEach(() => {
    ({ document } = parseHTML('<html><body><div id="agent-grid"></div></body></html>'));
    globalThis.document = document;
    clearAgents();
});

afterEach(() => {
    clearAgents();
});

function makeCard(lastSeen) {
    const card = document.createElement('div');
    card.dataset.lastSeen = lastSeen;
    document.getElementById('agent-grid').appendChild(card);
    return card;
}

test('capacity evicts the least recently seen card', () => {
    const newerCard = makeCard('200');
    const oldestCard = makeCard('100');
    const middleCard = makeCard('150');
    agents.newer = newerCard;
    agents.oldest = oldestCard;
    agents.middle = middleCard;

    assert.deepEqual(ensureAgentCapacity(3), ['oldest']);
    assert.deepEqual(Object.keys(agents).sort(), ['middle', 'newer']);
    assert.equal(document.body.contains(oldestCard), false);
    assert.equal(document.body.contains(newerCard), true);
    assert.equal(document.body.contains(middleCard), true);
});

test('capacity does nothing below the limit', () => {
    agents.only = makeCard('100');

    assert.deepEqual(ensureAgentCapacity(3), []);
    assert.ok(agents.only);
});

test('capacity evicts every surplus card after the limit is lowered', () => {
    agents.newest = makeCard('400');
    agents.oldest = makeCard('100');
    agents.newer = makeCard('300');
    agents.older = makeCard('200');

    assert.deepEqual(ensureAgentCapacity(2), ['oldest', 'older', 'newer']);
    assert.deepEqual(Object.keys(agents), ['newest']);
});

test('lowering the limit evicts the oldest surplus cards immediately', () => {
    const newestCard = makeCard('300');
    const oldestCard = makeCard('100');
    const middleCard = makeCard('200');
    agents.newest = newestCard;
    agents.oldest = oldestCard;
    agents.middle = middleCard;

    assert.deepEqual(evictAgents(1), ['oldest', 'middle']);
    assert.deepEqual(Object.keys(agents), ['newest']);
    assert.equal(document.body.contains(oldestCard), false);
    assert.equal(document.body.contains(middleCard), false);
    assert.equal(document.body.contains(newestCard), true);
    assert.deepEqual(evictAgents(1), []);
});

test('capacity breaks equal last-seen timestamps by lexical key', () => {
    const betaCard = makeCard('100');
    const alphaCard = makeCard('100');
    agents.beta = betaCard;
    agents.alpha = alphaCard;

    assert.deepEqual(ensureAgentCapacity(2), ['alpha']);
    assert.equal(document.body.contains(alphaCard), false);
    assert.equal(document.body.contains(betaCard), true);
});

test('capacity evicts the sole card when limit is one', () => {
    const onlyCard = makeCard('100');
    agents.only = onlyCard;

    assert.deepEqual(ensureAgentCapacity(1), ['only']);
    assert.deepEqual(Object.keys(agents), []);
    assert.equal(document.body.contains(onlyCard), false);
});
