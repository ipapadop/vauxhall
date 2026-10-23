// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

// Under --test-isolation=none every file shares one root, so a top-level
// hook runs around every test in the suite, not just its own file's.
const TOP_LEVEL_HOOK = /^(?:before|after)(?:Each)?\(/m;

test('no test file registers a top-level hook', () => {
    const directory = new URL('./', import.meta.url);
    const offenders = readdirSync(directory)
        .filter((name) => name.endsWith('.test.js'))
        .filter((name) => TOP_LEVEL_HOOK.test(readFileSync(new URL(name, directory), 'utf8')));

    assert.deepEqual(offenders, []);
});
