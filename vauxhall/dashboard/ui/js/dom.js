/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file dom.js
 * @description DOM helpers shared by the dashboard's modules.
 */

/**
 * Creates an element, optionally with a class and text content.
 * @param {string} tag - The tag name.
 * @param {string} [className] - Class applied to the element.
 * @param {unknown} [text] - Text content, when the element needs one;
 *   `null` gives empty text.
 * @returns {HTMLElement} The created element.
 */
export function element(tag, className = '', text = undefined) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text ?? '');
    return node;
}
