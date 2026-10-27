/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file motion.js
 * @description Reduced-motion checks and the pane's grow-from-card animation.
 */

const DEFAULT_SPEED_MS = 200;

/**
 * Returns whether the viewer asked for reduced motion.
 * @returns {boolean} Whether animations should be skipped.
 */
export const prefersReducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

/**
 * Parses a CSS time such as `0.2s` or `150ms`.
 * @param {string} value - The CSS time.
 * @returns {number} The time in milliseconds, or 200 when it can't be parsed.
 */
export function motionDuration(value) {
    const match = /^([\d.]+)(m?s)$/.exec(String(value).trim());
    const amount = match ? Number(match[1]) : NaN;
    if (!Number.isFinite(amount)) return DEFAULT_SPEED_MS;
    return match[2] === 's' ? amount * 1000 : amount;
}

/**
 * Animates an element from another rectangle, such as the card it expands,
 * to its own laid-out position and size.
 *
 * Takes twice `--transition-speed`, and is skipped under reduced motion,
 * without the Web Animations API, or when either rectangle is empty.
 * @param {HTMLElement} element - The element, already laid out at its final place.
 * @param {{left: number, top: number, width: number, height: number}} from - The start rectangle.
 * @returns {Animation | null} The running animation, or null when skipped.
 */
export function growFrom(element, from) {
    if (prefersReducedMotion() || typeof element.animate !== 'function') return null;
    const to = element.getBoundingClientRect();
    if (!from?.width || !from?.height || !to.width || !to.height) return null;

    const speed = window.getComputedStyle(document.documentElement).getPropertyValue('--transition-speed');
    const start = `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})`;
    return element.animate([
        { transform: start, transformOrigin: 'top left', opacity: 0.4 },
        { transform: 'none', transformOrigin: 'top left', opacity: 1 },
    ], { duration: 2 * motionDuration(speed), easing: 'cubic-bezier(0.2, 0, 0, 1)' });
}
