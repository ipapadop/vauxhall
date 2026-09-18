/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file settings.js
 * @description Settings dialog: renders configuration fields and saves changes through the Python bridge.
 */

import { selectOption } from './preferences.js';

const SECTION_TITLES = { mqtt: 'MQTT', logging: 'Logging', dashboard: 'Dashboard' };
const SOURCE_LABELS = { default: 'Default', file: 'File', environment: 'Environment' };
const APPLY_NOTES = {
    live: 'Applies immediately.',
    reconnect: 'Reconnects to the broker.',
    restart: 'Applies after a restart.',
};

/**
 * Returns the DOM id of a field's input.
 * @param {object} field - A settings field descriptor from the bridge.
 * @returns {string} The input id.
 */
const inputId = (field) => `setting-${field.section}-${field.name}`;
/**
 * Returns a field's name as a human-readable label.
 * @param {object} field - A settings field descriptor from the bridge.
 * @returns {string} The label text.
 */
const labelOf = (field) => field.name.replaceAll('_', ' ');

/**
 * Creates an element, optionally with a class and text content.
 * @param {string} tag - The tag name.
 * @param {string} [className] - Class applied to the element.
 * @param {unknown} [text] - Text content, when the element needs one.
 * @returns {HTMLElement} The created element.
 */
function element(tag, className = '', text = undefined) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}

/**
 * Shows or hides an element through the hidden attribute.
 * @param {HTMLElement} node - The element to toggle.
 * @param {boolean} hidden - Whether the element should be hidden.
 */
function setHidden(node, hidden) {
    if (hidden) node.setAttribute('hidden', '');
    else node.removeAttribute('hidden');
}

/**
 * Enables or disables a control through the disabled attribute.
 * @param {HTMLElement} node - The control to toggle.
 * @param {boolean} disabled - Whether the control should be disabled.
 */
function setDisabled(node, disabled) {
    if (disabled) node.setAttribute('disabled', '');
    else node.removeAttribute('disabled');
}

/**
 * Writes a value into an input, using the form its field type calls for.
 * @param {HTMLElement} input - The field's input.
 * @param {object} field - The settings field descriptor.
 * @param {unknown} value - The value to display.
 */
function setValue(input, field, value) {
    if (field.type === 'boolean') {
        input.checked = Boolean(value);
    } else if (field.choices) {
        selectOption(input, String(value));
    } else {
        input.value = String(value);
    }
}

/**
 * Reads an input back as its field's type; a blank integer reads as NaN.
 * @param {HTMLElement} input - The field's input.
 * @param {object} field - The settings field descriptor.
 * @returns {string | number | boolean} The entered value.
 */
function readValue(input, field) {
    if (field.type === 'boolean') return input.checked;
    if (field.type === 'integer') {
        const raw = input.value.trim();
        return raw === '' ? NaN : Number(raw);
    }
    return input.value;
}

/**
 * Checks a value against its field's type, range, and choices.
 * @param {object} field - The settings field descriptor.
 * @param {string | number | boolean} value - The entered value.
 * @returns {string} The error to show, or an empty string when valid.
 */
function validate(field, value) {
    if (field.type === 'integer') {
        if (!Number.isInteger(value)) return 'Enter a whole number.';
        if ((field.min !== null && value < field.min) || (field.max !== null && value > field.max)) {
            return `Enter a number from ${field.min} to ${field.max}.`;
        }
    }
    if (field.required && !value) return 'Enter a value.';
    if (field.choices && !field.choices.includes(value)) return `Choose one of ${field.choices.join(', ')}.`;
    return '';
}

/**
 * Returns the note explaining when a field applies, or why it is read-only.
 * @param {object} field - The settings field descriptor.
 * @returns {string} The note text.
 */
function noteFor(field) {
    if (field.editable) return APPLY_NOTES[field.apply] ?? '';
    if (field.source === 'environment') return `Set by ${field.location}.`;
    return 'Read-only: a configuration file in the current directory takes precedence.';
}

/**
 * Creates the input for a field, populated and disabled to match it.
 * @param {object} field - The settings field descriptor.
 * @returns {HTMLElement} The created input.
 */
function createInput(field) {
    let input;
    if (field.type === 'boolean') {
        input = element('input');
        input.setAttribute('type', 'checkbox');
    } else if (field.choices) {
        input = element('select', 'secondary-btn');
        for (const choice of field.choices) {
            const option = element('option', '', choice);
            option.setAttribute('value', choice);
            input.appendChild(option);
        }
    } else {
        input = element('input', 'search-bar');
        input.setAttribute('type', field.type === 'integer' ? 'number' : 'text');
        if (field.min !== null) input.setAttribute('min', String(field.min));
        if (field.max !== null) input.setAttribute('max', String(field.max));
        if (field.type === 'integer') input.setAttribute('step', '1');
    }
    input.id = inputId(field);
    input.setAttribute('name', field.key);
    setValue(input, field, field.value);
    setDisabled(input, !field.editable);
    return input;
}

/**
 * Creates a field's settings row: label, input, source badge, reset, and note.
 * @param {object} field - The settings field descriptor.
 * @returns {HTMLElement} The created row.
 */
function createRow(field) {
    const row = element('div', 'settings-row');
    row.dataset.key = field.key;

    const input = createInput(field);
    const label = element('label', 'settings-label', labelOf(field));
    label.setAttribute('for', input.id);

    const badge = element('span', `source-badge source-${field.source}`, SOURCE_LABELS[field.source] ?? field.source);
    if (field.location) badge.setAttribute('title', field.location);

    const reset = element('button', 'secondary-btn settings-reset', 'Reset');
    reset.setAttribute('type', 'button');
    reset.setAttribute('aria-label', `Reset ${labelOf(field)} to default`);
    setDisabled(reset, !field.editable);
    reset.addEventListener('click', () => {
        setValue(input, field, field.default);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const note = element('span', 'settings-note', noteFor(field));
    note.id = `${input.id}-note`;
    const error = element('span', 'settings-error');
    error.id = `${input.id}-error`;
    input.setAttribute('aria-describedby', `${note.id} ${error.id}`);

    row.append(label, input, badge, reset, note, error);
    return row;
}

/**
 * Renders one fieldset per configuration section.
 * @param {HTMLElement} container - Element that receives the fields.
 * @param {object} descriptor - Result of DashboardIPC.get_settings().
 */
export function renderSettingsForm(container, descriptor) {
    container.replaceChildren();
    for (const [section, title] of Object.entries(SECTION_TITLES)) {
        const sectionFields = descriptor.fields.filter(field => field.section === section);
        if (!sectionFields.length) continue;
        const fieldset = element('fieldset', 'settings-section');
        fieldset.appendChild(element('legend', '', title));
        sectionFields.forEach(field => fieldset.appendChild(createRow(field)));
        container.appendChild(fieldset);
    }
}

/**
 * Reads the editable fields, returning changed values and client-side errors.
 * @param {HTMLElement} container - Element holding the rendered fields.
 * @param {object} descriptor - Result of DashboardIPC.get_settings().
 * @returns {{changes: object, errors: object}} Changes grouped by section, and error messages keyed by "section.key".
 */
export function collectChanges(container, descriptor) {
    const changes = {};
    const errors = {};
    for (const field of descriptor.fields) {
        const input = field.editable && container.querySelector(`#${inputId(field)}`);
        if (!input) continue;
        const value = readValue(input, field);
        const error = validate(field, value);
        if (error) errors[field.key] = error;
        else if (value !== field.value) (changes[field.section] ??= {})[field.name] = value;
    }
    return { changes, errors };
}

/**
 * Returns the editable MQTT values in the form that differ from the values the hooks use.
 * @param {HTMLElement} container - Element holding the rendered fields.
 * @param {object} descriptor - Result of DashboardIPC.get_settings().
 * @returns {object} Changes for the hooks file, grouped by section.
 */
export function collectHookChanges(container, descriptor) {
    const mqtt = {};
    for (const field of descriptor.fields) {
        const input = field.section === 'mqtt' && field.editable && container.querySelector(`#${inputId(field)}`);
        if (!input) continue;
        const value = readValue(input, field);
        const hooksValue = descriptor.hooks_mqtt ? descriptor.hooks_mqtt[field.name] : field.value;
        if (!validate(field, value) && value !== hooksValue) mqtt[field.name] = value;
    }
    return Object.keys(mqtt).length ? { mqtt } : {};
}

/**
 * Shows error messages next to their fields and clears the others.
 * @param {HTMLElement} container - Element holding the rendered fields.
 * @param {object} errors - Error messages keyed by "section.key".
 */
export function showErrors(container, errors) {
    for (const row of container.querySelectorAll('.settings-row')) {
        const message = errors[row.dataset.key] ?? '';
        row.querySelector('.settings-error').textContent = message;
        const input = row.querySelector('input, select');
        if (message) input.setAttribute('aria-invalid', 'true');
        else input.removeAttribute('aria-invalid');
    }
}

/**
 * Describes what still needs attention after a successful save.
 * @param {object} result - Successful result of DashboardIPC.save_settings().
 * @returns {string} A message, or an empty string when nothing needs attention.
 */
export function savedNotes(result) {
    const notes = [];
    if (result.restart_required?.length) notes.push(`Restart Vauxhall to apply: ${result.restart_required.join(', ')}.`);
    if (result.hooks_error) notes.push(`Hooks configuration not updated: ${result.hooks_error}`);
    return notes.length ? `Saved. ${notes.join(' ')}` : '';
}

/**
 * Opens a dialog, falling back to the open attribute without showModal().
 * @param {HTMLDialogElement} dialog - The dialog to open.
 */
function openDialog(dialog) {
    if (typeof dialog.showModal === 'function') {
        if (!dialog.open) dialog.showModal();
    } else {
        dialog.setAttribute('open', '');
    }
}

/**
 * Closes a dialog, falling back to the open attribute without close().
 * @param {HTMLDialogElement} dialog - The dialog to close.
 */
function closeDialog(dialog) {
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
}

/**
 * Wires the settings button and dialog to the Python bridge.
 * @param {object} ipc - The DashboardIPC bridge.
 */
export function initSettings(ipc) {
    const button = document.getElementById('settings-btn');
    const dialog = document.getElementById('settings-dialog');
    const form = document.getElementById('settings-form');
    const container = document.getElementById('settings-fields');
    const message = document.getElementById('settings-message');
    const hooks = document.getElementById('settings-hooks');
    const updateHooks = document.getElementById('settings-update-hooks');
    const hooksPath = document.getElementById('settings-hooks-path');
    if (!button || !dialog || !form || !container || !message || !hooks || !updateHooks || !ipc?.get_settings) return;

    let descriptor = null;

    const refreshHooks = () => {
        setHidden(hooks, !collectHookChanges(container, descriptor).mqtt);
    };

    const load = async (text = '') => {
        descriptor = JSON.parse(await ipc.get_settings());
        if (descriptor.error) {
            container.replaceChildren();
            message.textContent = descriptor.error;
            setHidden(hooks, true);
            return;
        }
        renderSettingsForm(container, descriptor);
        message.textContent = text;
        if (hooksPath) hooksPath.textContent = descriptor.paths.hooks;
        updateHooks.checked = false;
        setDisabled(updateHooks, Boolean(descriptor.hooks_error));
        updateHooks.setAttribute('title', descriptor.hooks_error ?? '');
        refreshHooks();
    };

    button.addEventListener('click', async () => {
        try {
            await load();
        } catch (err) {
            console.error('Failed to load settings:', err);
            descriptor = null;
            container.replaceChildren();
            message.textContent = 'Could not load settings.';
        }
        openDialog(dialog);
    });

    container.addEventListener('input', () => { if (descriptor?.fields) refreshHooks(); });
    container.addEventListener('change', () => { if (descriptor?.fields) refreshHooks(); });
    document.getElementById('settings-cancel')?.addEventListener('click', () => closeDialog(dialog));
    dialog.addEventListener('close', () => button.focus());

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!descriptor?.fields) return;

        const { changes, errors } = collectChanges(container, descriptor);
        showErrors(container, errors);
        if (Object.keys(errors).length) {
            message.textContent = 'Fix the highlighted settings.';
            return;
        }
        const updateHookFile = updateHooks.checked && Boolean(collectHookChanges(container, descriptor).mqtt);
        if (!Object.keys(changes).length && !updateHookFile) {
            closeDialog(dialog);
            return;
        }

        let result;
        try {
            result = JSON.parse(await ipc.save_settings(JSON.stringify({
                changes,
                update_hooks: updateHookFile,
            })));
        } catch (err) {
            console.error('Failed to save settings:', err);
            message.textContent = 'Could not save settings.';
            return;
        }

        if (!result.ok) {
            if (result.field) showErrors(container, { [result.field]: result.error });
            message.textContent = result.file === 'hooks'
                ? `Nothing saved. Hooks configuration: ${result.error}`
                : `Nothing saved. ${result.error}`;
            return;
        }

        const notes = savedNotes(result);
        if (notes) await load(notes);
        else closeDialog(dialog);
    });
}
