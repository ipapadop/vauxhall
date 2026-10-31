/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file install.js
 * @description The Install Hooks dialog: pick a directory, choose its agents, and follow the installer's log.
 */

import { closeDialog, openDialog } from './dialog.js';
import { element } from './dom.js';

/**
 * Returns whether an agent starts ticked: found in the directory without hooks.
 * An installed agent is reinstalled only when the user asks.
 * @param {object} agent - A `detect_agents` entry.
 * @returns {boolean} Whether its checkbox starts checked.
 */
export function defaultChecked(agent) {
    return Boolean(agent.detected && !agent.installed && !agent.error);
}

/**
 * Describes an agent's state in the directory.
 * @param {object} agent - A `detect_agents` entry.
 * @returns {string} The text shown after its name.
 */
export function agentStatus(agent) {
    if (agent.error) return agent.error;
    if (agent.installed) return 'Hooks installed — Reinstall';
    return agent.detected ? 'Detected' : 'Not detected';
}

/**
 * Wires the Install Hooks button and dialog.
 * @param {object} ipc - The DashboardIPC bridge.
 * @returns {{onOutput: Function, onDone: Function} | null} Handlers for the
 *     `install-output` and `install-done` events, or null without the bridge or markup.
 */
export function initInstall(ipc) {
    const $ = (id) => document.getElementById(id);
    const button = $('install-hooks-btn');
    const dialog = $('install-dialog');
    const pathText = $('install-path');
    const list = $('install-agents');
    const error = $('install-error');
    const log = $('install-log');
    const outcome = $('install-outcome');
    const run = $('install-run');
    const another = $('install-another');
    const close = $('install-close');
    if (!ipc?.select_install_directory || !button || !dialog || !pathText || !list || !error || !log || !outcome || !run || !another || !close) {
        return null;
    }

    let path = null;
    let running = false;

    const checkboxes = () => [...list.querySelectorAll('input[type="checkbox"]')];

    const refreshControls = () => {
        for (const box of checkboxes()) box.disabled = running;
        run.disabled = running || !checkboxes().some(box => box.checked);
        another.disabled = running;
        close.disabled = running;
    };

    const renderAgents = (agents) => {
        for (const row of list.querySelectorAll('.install-agent')) row.remove();
        for (const agent of agents) {
            const row = element('div', 'install-agent');
            const box = element('input');
            box.type = 'checkbox';
            box.id = `install-agent-${agent.agent}`;
            box.value = agent.agent;
            box.checked = defaultChecked(agent);
            const label = element('label', '', `${agent.name} — ${agentStatus(agent)}`);
            label.setAttribute('for', box.id);
            row.append(box, label);
            list.append(row);
        }
        refreshControls();
    };

    /**
     * Asks for a directory and shows its agents, starting a fresh log.
     * @param {HTMLElement} errorTarget - Where a picker error is shown.
     * @returns {Promise<boolean>} Whether a directory was chosen.
     */
    const choose = async (errorTarget) => {
        let result;
        try {
            result = JSON.parse(await ipc.select_install_directory());
        } catch (err) {
            console.error('Failed to choose an install directory:', err);
            result = { ok: false, error: 'Could not choose a directory' };
        }
        if (!result.ok) {
            if (result.error && errorTarget) errorTarget.textContent = result.error;
            return false;
        }
        path = result.path;
        pathText.textContent = path;
        log.textContent = '';
        outcome.textContent = '';
        error.textContent = '';
        renderAgents(result.agents);
        return true;
    };

    button.addEventListener('click', async () => {
        // A running install keeps its directory; choosing another would
        // relabel its log and results.
        if (running || await choose($('js-status'))) openDialog(dialog);
    });
    another.addEventListener('click', () => choose(error));
    close.addEventListener('click', () => closeDialog(dialog));
    list.addEventListener('change', refreshControls);
    // A closed dialog would leave a running install with no visible owner.
    // Chromium can let a repeated Escape through despite preventDefault, so a
    // close during an install opens the dialog again.
    dialog.addEventListener('cancel', (event) => { if (running) event.preventDefault(); });
    dialog.addEventListener('close', () => {
        if (running) openDialog(dialog);
        else button.focus();
    });

    run.addEventListener('click', async () => {
        const agents = checkboxes().filter(box => box.checked).map(box => box.value);
        if (!path || !agents.length) return;
        running = true;
        error.textContent = '';
        log.textContent = '';
        outcome.textContent = 'Installing…';
        refreshControls();
        let result;
        try {
            result = JSON.parse(await ipc.install_hooks(JSON.stringify({ path, agents })));
        } catch (err) {
            console.error('Failed to start the hook install:', err);
            result = { ok: false, error: 'The install could not start' };
        }
        // On success, install-done ends the run; it may arrive before this reply.
        if (!result.ok) {
            running = false;
            outcome.textContent = '';
            error.textContent = result.error;
            refreshControls();
        }
    });

    return {
        onOutput: ({ line }) => {
            const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 1;
            log.append(document.createTextNode(`${line}\n`));
            if (atBottom) log.scrollTop = log.scrollHeight;
        },
        onDone: async ({ ok, returncode }) => {
            running = false;
            if (ok) outcome.textContent = 'Hooks installed.';
            else if (returncode === null || returncode === undefined) outcome.textContent = 'Install failed. See the log above.';
            else outcome.textContent = `Install failed (exit ${returncode}). See the log above.`;
            refreshControls();
            if (path && ipc.detect_agents) {
                try {
                    const result = JSON.parse(await ipc.detect_agents(path));
                    if (result.ok) renderAgents(result.agents);
                } catch (err) {
                    console.error('Failed to detect agents:', err);
                }
            }
            if (dialog.open || dialog.hasAttribute('open')) close.focus();
        },
    };
}
