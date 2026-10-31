/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file history.js
 * @description Renders the activity pane's timeline of a card's events.
 */

import { closeDialog, openDialog } from './dialog.js';
import { element } from './dom.js';
import { WAITING_STATES, appendDetails, getDetailsString, isPositiveNumber, stateCategory } from './card.js';
import { growFrom } from './motion.js';
import { cardIdentity, historyDurations } from './state.js';

// The shortest bar, as a percentage, so brief events stay visible.
const MIN_BAR_PERCENT = 2;

/**
 * Formats a duration as seconds, minutes and seconds, or hours and minutes.
 * @param {number} ms - The duration in milliseconds.
 * @returns {string} The formatted duration.
 */
export function formatDuration(ms) {
    const seconds = Math.floor(ms / 1000);
    if (seconds < 1) return '<1s';
    if (seconds < 60) return `${seconds}s`;
    const pad = (value) => String(value).padStart(2, '0');
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${pad(seconds % 60)}s`;
    return `${Math.floor(seconds / 3600)}h ${pad(Math.floor(seconds / 60) % 60)}m`;
}

let isInteractingWithModal = false;

/**
 * Builds one timeline row: time, state, details, and timing, over a bar.
 * @param {object} item - The history entry.
 * @param {number} duration - Milliseconds spent in the entry's state.
 * @param {string} width - The bar's CSS width.
 * @returns {HTMLElement} The row, remembering its entry as `historyEntry`.
 */
function historyRow(item, duration, width) {
    const row = document.createElement('div');
    row.className = `history-item state-${stateCategory(item.state)}`;
    row.historyEntry = item;
    row.appendChild(element('span', 'history-time', item.time));
    row.appendChild(element('span', 'history-state', item.state));
    const details = element('span', 'history-details', '');
    appendDetails(details, item);
    row.appendChild(details);
    const timing = element('span', 'history-timing', '');
    const durationLabel = element('span', 'history-duration', formatDuration(duration));
    durationLabel.title = 'Time in this state';
    timing.appendChild(durationLabel);
    if (isPositiveNumber(item.details?.duration)) {
        const toolLabel = element('span', 'history-tool-duration', `tool ${item.details.duration}s`);
        toolLabel.title = 'Duration reported by the tool';
        timing.appendChild(toolLabel);
    }
    row.appendChild(timing);
    // The bar repeats the duration label, so screen readers skip it.
    const bar = document.createElement('div');
    bar.className = 'history-bar';
    bar.setAttribute('aria-hidden', 'true');
    const fill = document.createElement('div');
    fill.className = 'history-bar-fill';
    fill.style.width = width;
    bar.appendChild(fill);
    row.appendChild(bar);
    return row;
}

/**
 * Populates and opens the history modal.
 * Supports real-time updates and resizable behavior.
 *
 * @param {string} agentKey - Unique key for the agent.
 * @param {object} agents - Global agents state object.
 * @param {boolean} isSilent - If true, updates content without forcing focus or jumping to bottom (unless already there).
 */
export function openHistoryModal(agentKey, agents, isSilent = false) {
    const card = agents[agentKey];
    if (!card || !card.history) return;

    // The header follows silent updates too, because the workspace can change;
    // unchanged text is left alone so a selection in it survives.
    const { agent, workspace, session_id: sessionId } = cardIdentity(card);
    const setText = (id, text) => {
        const element = document.getElementById(id);
        if (!element || element.textContent === text) return false;
        element.textContent = text;
        return true;
    };
    setText('modal-agent-name', agent);
    const pathChanged = setText('modal-agent-meta', `${workspace} · session ${sessionId}`);
    // A copy outcome describes the path shown when it was copied. A live
    // move replaces it with an announcement, since the header isn't live.
    if (!isSilent || pathChanged) {
        const copyStatus = document.getElementById('modal-copy-status');
        if (copyStatus) copyStatus.textContent = isSilent ? `Workspace changed to ${workspace}` : '';
    }

    const body = document.getElementById('modal-history-body');
    if (!body) return;

    // Check if user is at the bottom BEFORE updating content
    const isAtBottom = body.scrollHeight - body.scrollTop <= body.clientHeight + 50;
    const oldScrollTop = body.scrollTop;

    // Initialize interaction listeners (only once)
    if (!body.hasListeners) {
        body.addEventListener('pointerdown', () => { isInteractingWithModal = true; });
        window.addEventListener('pointerup', () => { isInteractingWithModal = false; });
        window.addEventListener('pointercancel', () => { isInteractingWithModal = false; });
        body.hasListeners = true;
    }

    const searchTerm = document.getElementById('modal-search')?.value.toLowerCase() || '';
    const stateFilter = document.getElementById('modal-state-filter')?.value || 'ALL';

    // Durations come from the whole history, so a filter can't merge rows.
    const durations = historyDurations(card.history);
    const rows = card.history
        .map((item, index) => ({ item, duration: durations[index], open: index === 0 }))
        .filter(({ item }) => {
            const matchesSearch = getDetailsString(item).toLowerCase().includes(searchTerm);
            const matchesState = stateFilter === 'ALL' || item.state === stateFilter || (stateFilter === 'Waiting for Input' && WAITING_STATES.has(item.state));
            return matchesSearch && matchesState;
        })
        .reverse(); // Oldest at the top, newest at the bottom.
    // The newest entry lasts until now, so on a quiet card it would dwarf
    // every finished one; bars scale to the finished entries when any are shown.
    const finished = rows.filter(({ open }) => !open);
    const longest = Math.max(0, ...(finished.length ? finished : rows).map(({ duration }) => duration));
    const barWidth = (duration) => `${longest === 0 ? 0 : Math.min(100, Math.max(MIN_BAR_PERCENT, (duration / longest) * 100))}%`;

    // The same entries are updated in place, so the staleness sweep keeps a
    // text selection and the bars animate; anything else is rebuilt.
    const shown = [...body.children];
    if (shown.length === rows.length && shown.every((row, index) => row.historyEntry === rows[index].item)) {
        rows.forEach(({ duration }, index) => {
            shown[index].querySelector('.history-duration').textContent = formatDuration(duration);
            shown[index].querySelector('.history-bar-fill').style.width = barWidth(duration);
        });
    } else {
        body.replaceChildren(...rows.map(({ item, duration }) => historyRow(item, duration, barWidth(duration))));
    }

    const isInteracting = body.matches(':hover') || isInteractingWithModal;

    if (!isSilent) {
        // Initial open: Show modal and jump to latest event
        const historyModal = document.getElementById('history-modal');
        if (historyModal) {
            openDialog(historyModal);
            const content = historyModal.querySelector('.modal-content');
            if (content) growFrom(content, card.getBoundingClientRect());
        }
        body.scrollTop = body.scrollHeight;
    } else if (isAtBottom && !isInteracting) {
        // Live update: Only follow tail if user was already at the bottom and isn't hovering
        body.scrollTop = body.scrollHeight;
    } else {
        // Freeze mode: Restore scroll position to prevent jumping during DOM refresh
        body.scrollTop = oldScrollTop;
    }
}

/**
 * Closes the history modal.
 */
export function closeHistoryModal() {
    const historyModal = document.getElementById('history-modal');
    if (historyModal) closeDialog(historyModal);
}
