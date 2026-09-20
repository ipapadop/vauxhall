// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { createCard } from '../../../vauxhall/dashboard/ui/js/ui.js';

let copied = [];
let result = true;

const ipc = {
    DashboardIPC: {
        copy_to_clipboard: async (path) => {
            copied.push(path);
            return result;
        },
    },
};

/**
 * Builds an empty page and resets the recorded clipboard writes. Called from
 * each test rather than a shared hook, so a hook in another test file cannot
 * replace the document mid-test.
 */
function setupPage() {
    const { document, window } = parseHTML('<html><body></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    copied = [];
    result = true;
}

/**
 * Clicks a card for the given workspace and waits for the copy to settle.
 * @param {string} workspace - The workspace path the card reports.
 * @returns {Promise<HTMLElement>} The clicked card.
 */
async function clickCardFor(workspace) {
    const card = createCard({ agent: 'Codex', workspace, session_id: 'session-1' }, ipc, () => {});
    card.click();
    await new Promise((resolve) => setImmediate(resolve));
    return card;
}

/**
 * Returns the environment badge text of a card for the given workspace.
 * @param {string} workspace - The workspace path the card reports.
 * @param {string} [env] - An explicit environment from the telemetry.
 * @returns {string} The badge text.
 */
function envFor(workspace, env) {
    const card = createCard({ agent: 'Codex', workspace, session_id: 's', env }, null, () => {});
    return card.querySelector('.env-badge').textContent;
}

const PATHS = {
    'a POSIX home path': '/home/user/project',
    'a POSIX path outside home': '/srv/builds/nightly',
    'a Windows drive path': 'C:\\Users\\dev\\My Project',
    'a lowercase Windows drive path': 'd:\\work\\repo',
    'a Windows UNC share': '\\\\build-server\\share\\repo',
    'a path with spaces and quotes': '/home/user/my "quoted" project',
    'a path with a single quote': "/home/user/o'brien/project",
    'a command substitution': '/home/user/$(rm -rf ~)',
    'a backtick substitution': '/home/user/`id`',
    'a shell separator': '/home/user/project; rm -rf /',
    'a pipe and redirect': '/home/user/project | tee /tmp/out > /dev/null',
    'an embedded newline': '/home/user/project\nrm -rf /',
    'a variable reference': '/home/user/$HOME/${PATH}',
    'a glob': '/home/user/*/../../etc/passwd',
    'a percent expansion': 'C:\\Users\\%USERNAME%\\project',
    'a null-looking escape': '/home/user/project\\0/etc',
    'a non-ASCII path': '/home/user/проект/ファイル',
};

for (const [description, workspace] of Object.entries(PATHS)) {
    test(`${description} is copied exactly as received`, async () => {
        setupPage();
        await clickCardFor(workspace);

        assert.deepEqual(copied, [workspace]);
    });
}

test('the copied path is the telemetry value, not the displayed one', async () => {
    setupPage();
    const workspace = '/home/user/project\nrm -rf /';

    const card = await clickCardFor(workspace);

    assert.equal(card.querySelector('.agent-workspace').textContent, workspace);
    assert.equal(copied[0], workspace);
    assert.equal(copied[0].includes('\n'), true);
});

test('a missing workspace copies an empty string', async () => {
    setupPage();
    const card = createCard({ agent: 'Codex', session_id: 's' }, ipc, () => {});

    card.click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.deepEqual(copied, ['']);
});

test('a successful copy highlights the card', async () => {
    setupPage();
    const card = await clickCardFor('/home/user/project');

    assert.equal(card.classList.contains('copied'), true);
});

test('a refused copy leaves the card unhighlighted', async () => {
    setupPage();
    result = false;

    const card = await clickCardFor('/home/user/project');

    assert.equal(card.classList.contains('copied'), false);
});

test('a card without a clipboard bridge ignores the click', () => {
    setupPage();
    const card = createCard({ agent: 'Codex', workspace: '/home/user/p', session_id: 's' }, null, () => {});

    assert.doesNotThrow(() => card.click());
});

test('the history icon does not trigger a copy', async () => {
    setupPage();
    let opened = 0;
    const card = createCard(
        { agent: 'Codex', workspace: '/home/user/project', session_id: 's' },
        ipc,
        () => { opened += 1; },
    );

    card.querySelector('.history-icon').click();
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(opened, 1);
    assert.deepEqual(copied, []);
});

test('POSIX home and Windows drive paths are labeled local', () => {
    setupPage();
    assert.equal(envFor('/home/user/project'), 'local');
    assert.equal(envFor('C:\\Users\\dev\\project'), 'local');
    assert.equal(envFor('d:\\work\\repo'), 'local');
});

test('other paths, including UNC shares, are labeled remote', () => {
    setupPage();
    assert.equal(envFor('/srv/builds/nightly'), 'remote');
    assert.equal(envFor('\\\\build-server\\share\\repo'), 'remote');
    assert.equal(envFor('/homework/not-a-home'), 'local');
});

test('a reported environment overrides the path-based guess', () => {
    setupPage();
    assert.equal(envFor('/home/user/project', 'remote'), 'remote');
    assert.equal(envFor('/srv/builds', 'local'), 'local');
    assert.equal(envFor('/srv/builds', 'elsewhere'), 'remote');
});
