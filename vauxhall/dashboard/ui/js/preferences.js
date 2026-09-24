/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file preferences.js
 * @description Loads and saves view preferences (theme, sort order, history filter) through the Python bridge.
 */

// Earlier versions stored the theme only here; it now caches the theme for the first paint.
const THEME_CACHE_KEY = 'vauxhall-theme';
const SAVE_DELAY_MS = 500;

/**
 * Returns whether a value is one of the supported theme names.
 * @param {unknown} value - The candidate theme.
 * @returns {boolean} Whether the value is a theme.
 */
export const isTheme = (value) => value === 'dark' || value === 'light';

/**
 * Returns the theme cached in localStorage, if any.
 * @returns {string | null} The cached theme.
 */
export function cachedTheme() {
    try {
        return globalThis.localStorage?.getItem(THEME_CACHE_KEY) ?? null;
    } catch {
        return null;
    }
}

/**
 * Caches the theme in localStorage so the next start paints with it before preferences load.
 * @param {string} theme - The theme to cache.
 */
export function cacheTheme(theme) {
    try {
        globalThis.localStorage?.setItem(THEME_CACHE_KEY, theme);
    } catch {
        // Storage is unavailable; the state file still records the theme.
    }
}

/**
 * Selects the option with the given value, if the select has one.
 * Selecting one option deselects the others in a single-choice select.
 * @param {HTMLSelectElement | null} select - The select element.
 * @param {string} value - The option value.
 * @returns {boolean} Whether an option was selected.
 */
export function selectOption(select, value) {
    const option = [...(select?.options ?? [])].find(candidate => candidate.value === value);
    if (option) option.selected = true;
    return Boolean(option);
}

/**
 * Loads saved preferences from the Python bridge.
 * @param {object} ipc - The DashboardIPC bridge.
 * @returns {Promise<object>} The saved preferences, or an empty object.
 */
export async function loadPreferences(ipc) {
    if (!ipc?.get_ui_state) return {};
    try {
        const preferences = JSON.parse(await ipc.get_ui_state());
        return preferences && typeof preferences === 'object' && !Array.isArray(preferences) ? preferences : {};
    } catch (err) {
        console.error('Failed to load preferences:', err);
        return {};
    }
}

/**
 * Creates a saver that batches preference changes and sends them after a pause.
 * @param {object} ipc - The DashboardIPC bridge.
 * @returns {{save: (changes: object) => void, flush: () => void}} Queues changes, or sends queued changes now.
 */
export function createPreferenceSaver(ipc) {
    let pending = {};
    let timer = null;

    const flush = () => {
        clearTimeout(timer);
        timer = null;
        if (!ipc?.save_ui_state || !Object.keys(pending).length) return;
        const payload = pending;
        pending = {};
        Promise.resolve(ipc.save_ui_state(JSON.stringify(payload)))
            .then(saved => { if (saved === false) console.error('Failed to save preferences'); })
            .catch(err => console.error('Failed to save preferences:', err));
    };

    const save = (changes) => {
        if (!ipc?.save_ui_state) return;
        Object.assign(pending, changes);
        clearTimeout(timer);
        timer = setTimeout(flush, SAVE_DELAY_MS);
    };

    return { save, flush };
}

/**
 * Applies saved preferences the user hasn't already changed, and copies a
 * theme cached by earlier versions into the state file.
 * @param {object} ipc - The DashboardIPC bridge.
 * @param {object} view - Current state, callbacks, and elements to update.
 * @param {string | null} view.cached - The theme cached in localStorage.
 * @param {Set<string>} view.changed - Preferences the user changed before loading finished.
 * @param {(theme: string) => void} view.applyTheme - Applies a theme.
 * @param {(sort: string, attentionFirst: boolean) => void} view.applySort - Re-sorts the cards after a sort order or the attention-first toggle is restored.
 * @param {(changes: object) => void} view.save - Saves preference changes.
 * @param {HTMLSelectElement | null} view.sortSelect - The card sort select.
 * @param {HTMLSelectElement | null} view.historyFilter - The history state filter select.
 * @param {HTMLInputElement | null} [view.attentionFirstToggle] - The "Attention first" checkbox.
 * @param {HTMLInputElement | null} [view.notifyToggle] - The "Notify me" checkbox.
 */
export async function restorePreferences(ipc, { cached, changed, applyTheme, applySort, save, sortSelect, historyFilter, attentionFirstToggle, notifyToggle }) {
    const preferences = await loadPreferences(ipc);
    const restore = (key) => Object.hasOwn(preferences, key) && !changed.has(key);

    if (restore('theme') && isTheme(preferences.theme)) {
        applyTheme(preferences.theme);
    } else if (!isTheme(preferences.theme) && isTheme(cached) && !changed.has('theme')) {
        save({ theme: cached });
    }

    const attentionFirstRestored = restore('attention_first') && Boolean(attentionFirstToggle);
    if (attentionFirstRestored) attentionFirstToggle.checked = Boolean(preferences.attention_first);
    const sortRestored = restore('sort') && selectOption(sortSelect, preferences.sort);
    if (sortRestored || attentionFirstRestored) applySort(sortSelect?.value, Boolean(attentionFirstToggle?.checked));

    if (restore('history_filter')) selectOption(historyFilter, preferences.history_filter);
    if (restore('notify') && notifyToggle) notifyToggle.checked = Boolean(preferences.notify);
}
