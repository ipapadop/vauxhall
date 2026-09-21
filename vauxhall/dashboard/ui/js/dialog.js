/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file dialog.js
 * @description Opening and closing native dialogs, with a fallback for environments without them.
 */

/**
 * Opens a dialog modally, falling back to the open attribute without showModal().
 * @param {HTMLDialogElement} dialog - The dialog to open.
 */
export function openDialog(dialog) {
    if (typeof dialog.showModal === 'function') {
        if (!dialog.open) dialog.showModal();
    } else {
        dialog.setAttribute('open', '');
    }
}

/**
 * Closes a dialog, falling back to the open attribute without close().
 * The fallback dispatches the close event the browser would fire, so callers
 * can restore focus and view state in one place.
 * @param {HTMLDialogElement} dialog - The dialog to close.
 */
export function closeDialog(dialog) {
    if (typeof dialog.close === 'function') {
        dialog.close();
    } else if (dialog.hasAttribute('open')) {
        dialog.removeAttribute('open');
        // The event must come from the dialog's own document so listeners
        // registered on it recognize it.
        const DialogEvent = dialog.ownerDocument?.defaultView?.Event ?? Event;
        dialog.dispatchEvent(new DialogEvent('close'));
    }
}
