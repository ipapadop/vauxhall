// SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseHTML } from 'linkedom';

import { growFrom, motionDuration } from '../../../vauxhall/dashboard/ui/js/motion.js';

const CARD = { left: 10, top: 20, width: 100, height: 50 };
const PANE = { left: 110, top: 70, width: 400, height: 200 };

/**
 * Builds a page with an element laid out at the pane's final rectangle that
 * records its animations. Called from each test rather than a shared hook.
 * @param {object} [options] - Page options.
 * @param {boolean} [options.reducedMotion] - Whether reduced motion is preferred.
 * @param {string} [options.speed] - The computed `--transition-speed`.
 * @returns {{element: HTMLElement, animations: Array<{keyframes: object[], options: object}>}}
 *   The element and the animations started on it.
 */
function setupPage({ reducedMotion = false, speed = '0.2s' } = {}) {
    const { document, window } = parseHTML('<html><body><div id="pane"></div></body></html>');
    globalThis.document = document;
    globalThis.window = window;
    window.matchMedia = (query) => ({ matches: reducedMotion && query === '(prefers-reduced-motion: reduce)' });
    window.getComputedStyle = () => ({ getPropertyValue: (name) => (name === '--transition-speed' ? speed : '') });
    const element = document.getElementById('pane');
    element.getBoundingClientRect = () => PANE;
    const animations = [];
    element.animate = (keyframes, options) => {
        animations.push({ keyframes, options });
        return { keyframes, options };
    };
    return { element, animations };
}

test('the pane grows from the card rectangle to its own', () => {
    const { element, animations } = setupPage();

    growFrom(element, CARD);

    assert.equal(animations.length, 1);
    const [{ keyframes }] = animations;
    assert.equal(keyframes[0].transform, 'translate(-100px, -50px) scale(0.25, 0.25)');
    assert.equal(keyframes[0].transformOrigin, 'top left');
    assert.equal(keyframes.at(-1).transform, 'none');
});

test('the animation lasts twice the transition speed', () => {
    const { element, animations } = setupPage({ speed: '0.3s' });

    growFrom(element, CARD);

    assert.equal(animations[0].options.duration, 600);
});

test('reduced motion skips the animation', () => {
    const { element, animations } = setupPage({ reducedMotion: true });

    assert.equal(growFrom(element, CARD), null);
    assert.equal(animations.length, 0);
});

test('an element without the Web Animations API is left alone', () => {
    const { element } = setupPage();
    element.animate = undefined;

    assert.equal(growFrom(element, CARD), null);
});

test('an empty start or end rectangle skips the animation', () => {
    const { element, animations } = setupPage();

    growFrom(element, { left: 0, top: 0, width: 0, height: 0 });
    element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 0, height: 0 });
    growFrom(element, CARD);

    assert.equal(animations.length, 0);
});

test('motion durations parse seconds and milliseconds, defaulting to 0.2s', () => {
    assert.equal(motionDuration('0.2s'), 200);
    assert.equal(motionDuration(' 150ms '), 150);
    assert.equal(motionDuration('0.01ms'), 0.01);
    assert.equal(motionDuration(''), 200);
    assert.equal(motionDuration('fast'), 200);
});
