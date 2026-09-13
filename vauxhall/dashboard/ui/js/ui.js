/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file ui.js
 * @description Handles DOM manipulation, card creation, and updates.
 */

const WAITING_STATES = new Set(['Waiting', 'Waiting for Input', 'Input Required']);
const STATUS_ORDER = { 'Error': 0, 'Waiting': 1, 'Input Required': 1, 'Waiting for Input': 1, 'Acting': 2, 'Thinking': 2, 'Idle': 3, 'STALE': 4 };

const isPositiveNumber = (value) => typeof value === 'number' && Number.isFinite(value) && value > 0;
const textOf = (card, selector) => card.querySelector(selector)?.textContent || '';
const tokensOf = (card) => parseInt(card.querySelector('.metric-badge.tokens')?.dataset.value || '0');

const CARD_COMPARATORS = {
    name: (a, b) => textOf(a, '.agent-name').localeCompare(textOf(b, '.agent-name')),
    recent: (a, b) => parseInt(b.dataset.lastSeen || '0') - parseInt(a.dataset.lastSeen || '0'),
    status: (a, b) => (STATUS_ORDER[textOf(a, '.status-badge')] ?? 9) - (STATUS_ORDER[textOf(b, '.status-badge')] ?? 9),
    tokens: (a, b) => tokensOf(b) - tokensOf(a),
};

function textSpan(className, value) {
    const span = document.createElement('span');
    span.className = className;
    span.textContent = String(value ?? '');
    return span;
}

/**
 * Creates an agent card element.
 * @param {object} data - Initial telemetry data.
 * @param {any} pyloidIpc - Pyloid IPC bridge.
 * @param {Function} openHistoryCallback - Function to call when history icon is clicked.
 * @returns {HTMLElement} The created card.
 */
export function createCard(data, pyloidIpc, openHistoryCallback) {
    const agent = String(data.agent ?? '');
    const workspace = String(data.workspace ?? '');
    const sessionId = String(data.session_id ?? '');
    const configuredEnv = data.env === 'local' || data.env === 'remote' ? data.env : null;
    const env = configuredEnv || (workspace.startsWith('/home') || /^[A-Z]:\\/i.test(workspace) ? 'local' : 'remote');

    const card = document.createElement('div');
    card.className = 'agent-card';
    card.title = "Click to copy workspace path";
    card.innerHTML = `
        <div class="agent-header">
            <div class="agent-info">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="env-badge" title="Execution environment"></span>
                    <div class="agent-name" title="Agent name"></div>
                </div>
                <div class="agent-workspace" title="Current workspace path"></div>
                <div class="agent-session" title="Agent session identifier"></div>
            </div>
            <div class="status-badge" title="Current agent state">Idle</div>
        </div>

        <div class="log-area" title="Real-time operations log (shows last 5 events)">Ready...</div>
        <div class="agent-footer">
            <div class="footer-meta">
                <span class="last-seen-timer" title="Time since last activity">just now</span>
                <div class="metric-badges" title="Recent operation metrics"></div>
            </div>
            <span class="history-icon" title="View historical operations">🕒</span>
        </div>
    `;

    const envBadge = card.querySelector('.env-badge');
    envBadge.classList.add(`env-${env}`);
    envBadge.textContent = env;
    card.querySelector('.agent-name').textContent = agent;
    card.querySelector('.agent-workspace').textContent = workspace;
    const sessionElement = card.querySelector('.agent-session');
    sessionElement.textContent = `Session: ${sessionId}`;
    sessionElement.title = sessionId;

    card.querySelector('.history-icon').addEventListener('click', (e) => {
        e.stopPropagation();
        openHistoryCallback();
    });

    // Copy the raw workspace path; never build a shell command from it
    card.addEventListener('click', () => {
        pyloidIpc?.DashboardIPC?.copy_to_clipboard(workspace).then((success) => {
            if (success) showCopyFeedback(card);
        });
    });

    return card;
}

/**
 * Builds the display segments that describe a telemetry event.
 * @param {object} data - The telemetry data object (containing state and details).
 * @returns {Array<{text: string, className?: string}>} Display segments.
 */
function getDetailsSegments(data) {
    if (!data) return [];
    const details = data.details && typeof data.details === 'object' ? data.details : {};
    const state = data.state;
    const segment = (value, className) => ({ text: String(value), className });
    const promptSegments = () => [segment('Prompt:', 'log-prompt'), segment(` ${details.prompt}`)];

    // Prioritize prompt for waiting states
    if (WAITING_STATES.has(state)) {
        if (details.prompt) return promptSegments();
        if (details.message) return [segment(details.message)];
    }

    if (details.error) {
        return [segment('Error:', 'log-error'), segment(` ${details.error}`)];
    }

    if (details.tool) {
        // If it's a known placeholder, and we have something better, use it
        if (details.tool === 'unknown' || details.tool === 'unknown_tool') {
            if (details.prompt) return promptSegments();
            if (details.status) return [segment(details.status)];
        }

        // For AfterTool (Thinking state), show "Completed"
        if (state === 'Thinking' && details.status === 'completed') {
            return [segment('Completed:', 'log-completed'), segment(` ${details.tool}`, 'log-tool')];
        }

        const segments = [segment('Running:', 'log-acting'), segment(` ${details.tool}`, 'log-tool')];
        if (details.cmd) segments.push(segment(` ${details.cmd}`, 'log-cmd'));
        return segments;
    }

    if (details.prompt) return promptSegments();
    if (details.status) return [segment(details.status)];
    return [];
}

function getDetailsString(data) {
    return getDetailsSegments(data).map(segment => segment.text).join('');
}

function appendDetails(container, data) {
    getDetailsSegments(data).forEach(({ text, className }) => {
        container.appendChild(className ? textSpan(className, text) : document.createTextNode(text));
    });
}

/**
 * Updates an agent card with new telemetry.
 * Handles state styles, metrics, and the 5-event rolling log.
 * @param {HTMLElement} card - The agent card element.
 * @param {object} data - The telemetry data.
 */
export function updateCard(card, data) {
    const statusBadge = card.querySelector('.status-badge');
    const logArea = card.querySelector('.log-area');
    const metricsArea = card.querySelector('.metric-badges');

    if (statusBadge) statusBadge.textContent = data.state;

    // Update color-coded state classes
    card.classList.remove('error', 'waiting', 'working');
    if (data.state === 'Error') {
        card.classList.add('error');
    } else if (WAITING_STATES.has(data.state)) {
        card.classList.add('waiting');
    } else if (data.state === 'Acting' || data.state === 'Thinking') {
        card.classList.add('working');
    }

    const details = data.details || {};

    // Reset metrics when starting a new operation
    if (data.state === 'Acting' || (data.state === 'Thinking' && details.prompt)) {
        card.latestTokens = null;
        card.latestDuration = null;
    }
    if (isPositiveNumber(details.tokens)) card.latestTokens = details.tokens;
    if (isPositiveNumber(details.duration)) card.latestDuration = details.duration;

    // Update Footer Metric Badges
    if (metricsArea) {
        metricsArea.replaceChildren();
        if (card.latestTokens) {
            const tokens = card.latestTokens > 1000 ? `${(card.latestTokens / 1000).toFixed(1)}k` : card.latestTokens;
            const badge = textSpan('metric-badge tokens', tokens);
            badge.dataset.value = String(card.latestTokens);
            badge.title = 'Tokens used in last operation';
            metricsArea.appendChild(badge);
        }
        if (card.latestDuration) {
            const badge = textSpan('metric-badge', `${card.latestDuration}s`);
            badge.title = 'Duration of last operation';
            metricsArea.appendChild(badge);
        }
    }

    // Update Rolling Activity Log (last 5 entries)
    const newLogMessage = getDetailsString(data);
    if (!newLogMessage || newLogMessage === card.lastLogMessage || !logArea) return;
    card.lastLogMessage = newLogMessage;

    const time = new Date().toLocaleTimeString([], {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    if (logArea.textContent === "Ready...") {
        logArea.replaceChildren();
    }

    const logLine = document.createElement('div');
    logLine.className = 'log-line';
    const timestamp = document.createElement('span');
    timestamp.style.color = 'var(--text-dim)';
    timestamp.textContent = `[${time}] `;
    logLine.appendChild(timestamp);
    appendDetails(logLine, data);
    logArea.prepend(logLine);

    // Enforce 5-event limit for the card view (remove oldest from bottom)
    while (logArea.children.length > 5) {
        logArea.removeChild(logArea.lastElementChild);
    }

    // Keep view at the top (newest)
    logArea.scrollTop = 0;
}

/**
 * Shows "Copied!" feedback on a card.
 * @param {HTMLElement} card - The agent card element.
 */
function showCopyFeedback(card) {
    card.classList.add('copied');
    setTimeout(() => card.classList.remove('copied'), 2000);
}

/**
 * Filters the agent grid.
 * @param {string} query - The search query.
 * @param {object} agents - The agents state object.
 */
export function filterGrid(query, agents) {
    Object.values(agents).forEach(card => {
        const nameElement = card.querySelector('.agent-name');
        const workspaceElement = card.querySelector('.agent-workspace');
        if (!nameElement || !workspaceElement) return;

        const name = nameElement.textContent?.toLowerCase() || '';
        const workspace = workspaceElement.textContent?.toLowerCase() || '';
        card.style.display = name.includes(query) || workspace.includes(query) ? 'flex' : 'none';
    });
}

/**
 * Sorts the agent grid.
 * @param {string} criteria - The sort criteria.
 * @param {HTMLElement} grid - The agent grid element.
 */
export function sortGrid(criteria, grid) {
    const cardsArray = Array.from(grid.children);

    // FIRST: Record positions
    const firstPositions = cardsArray.map(card => {
        const rect = card.getBoundingClientRect();
        return { card, top: rect.top, left: rect.left };
    });

    // LAST: Re-sort DOM
    const compare = Object.hasOwn(CARD_COMPARATORS, criteria) ? CARD_COMPARATORS[criteria] : () => 0;
    cardsArray.sort(compare).forEach(card => grid.appendChild(card));

    // INVERT & PLAY
    requestAnimationFrame(() => {
        firstPositions.forEach(({ card, top, left }) => {
            const rect = card.getBoundingClientRect();
            const deltaX = left - rect.left;
            const deltaY = top - rect.top;
            if (deltaX === 0 && deltaY === 0) return;

            card.style.transition = 'none';
            card.style.transform = `translate(${deltaX}px, ${deltaY}px)`;

            requestAnimationFrame(() => {
                // Use CSS variable for consistent speed
                card.style.transition = 'transform var(--transition-speed) ease-out';
                card.style.transform = '';

                // Clear styles after transition to restore CSS hover etc.
                card.addEventListener('transitionend', () => {
                    card.style.transition = '';
                    card.style.transform = '';
                }, { once: true });
            });
        });
    });
}

/**
 * Checks for stale agents and updates the last seen timer.
 * @param {object} agents - The agents state object.
 * @param {number} staleThresholdMs - The staleness threshold in milliseconds.
 */
export function checkStaleness(agents, staleThresholdMs = 120000) {
    const now = Date.now();

    Object.values(agents).forEach(card => {
        const diff = now - parseInt(card.dataset.lastSeen || '0');

        const timer = card.querySelector('.last-seen-timer');
        if (timer) {
            timer.textContent = diff < 60000 ? 'just now' : `${Math.floor(diff / 60000)}m ago`;
        }

        const isStale = diff > staleThresholdMs;
        card.classList.toggle('stale', isStale);
        const statusBadge = card.querySelector('.status-badge');
        if (isStale && statusBadge) statusBadge.textContent = 'STALE';
    });
}

let isInteractingWithModal = false;

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

    if (!isSilent) {
        const modalAgentName = document.getElementById('modal-agent-name');
        if (modalAgentName) modalAgentName.textContent = `History: ${agentKey}`;
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

    const filteredHistory = card.history.filter(item => {
        const matchesSearch = getDetailsString(item).toLowerCase().includes(searchTerm);
        const matchesState = stateFilter === 'ALL' || item.state === stateFilter || (stateFilter === 'Waiting' && item.state === 'Waiting for Input');
        return matchesSearch && matchesState;
    });

    // Re-render timeline items in chronological order (oldest top, newest bottom)
    body.replaceChildren();
    filteredHistory.reverse().forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.appendChild(textSpan('history-time', item.time));
        historyItem.appendChild(textSpan('history-state', item.state));
        const details = textSpan('history-details', '');
        appendDetails(details, item);
        historyItem.appendChild(details);
        body.appendChild(historyItem);
    });

    const isInteracting = body.matches(':hover') || isInteractingWithModal;

    if (!isSilent) {
        // Initial open: Show modal and jump to latest event
        const historyModal = document.getElementById('history-modal');
        if (historyModal) historyModal.style.display = "block";
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
    if (historyModal) historyModal.style.display = "none";
}
