/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file ui.js
 * @description Handles DOM manipulation, card creation, and updates.
 */

import { closeDialog, openDialog } from './dialog.js';

const WAITING_STATES = new Set(['Waiting', 'Waiting for Input', 'Input Required']);
const STATUS_ORDER = { 'Error': 0, 'Waiting': 1, 'Input Required': 1, 'Waiting for Input': 1, 'Acting': 2, 'Thinking': 2, 'Idle': 3, 'STALE': 4 };
// States that need a human: an active error, or a prompt/permission the agent is blocked on.
const ATTENTION_STATES = new Set([...WAITING_STATES, 'Error']);

/**
 * Returns whether a value is a finite number above zero.
 * @param {unknown} value - The candidate number.
 * @returns {boolean} Whether the value is usable as a positive metric.
 */
const isPositiveNumber = (value) => typeof value === 'number' && Number.isFinite(value) && value > 0;
/**
 * Returns the text of a card's first matching element, or an empty string.
 * @param {HTMLElement} card - The agent card.
 * @param {string} selector - Selector for the element to read.
 * @returns {string} The element's text.
 */
const textOf = (card, selector) => card.querySelector(selector)?.textContent || '';
/**
 * Returns a card's token count, or zero when it has no token badge.
 * @param {HTMLElement} card - The agent card.
 * @returns {number} The token count.
 */
const tokensOf = (card) => parseInt(card.querySelector('.metric-badge.tokens')?.dataset.value || '0');
/**
 * Returns whether a card is in a state that needs a human. Reads the
 * 'error'/'waiting' state classes rather than the status badge text, since
 * checkStaleness overwrites the badge to "STALE" but leaves those classes
 * alone — a card blocked long enough to go stale still needs attention.
 * @param {HTMLElement} card - The agent card.
 * @returns {boolean} Whether the card needs attention.
 */
const isAttentionCard = (card) => card.classList.contains('error') || card.classList.contains('waiting');
/**
 * Formats a token count, abbreviating counts over 1000.
 * @param {number} count - The token count.
 * @returns {string} The formatted count.
 */
const formatTokens = (count) => count > 1000 ? `${(count / 1000).toFixed(1)}k` : String(count);

/**
 * Returns whether the viewer asked for reduced motion.
 * @returns {boolean} Whether animations should be skipped.
 */
const prefersReducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

const CARD_COMPARATORS = {
    name: (a, b) => textOf(a, '.agent-name').localeCompare(textOf(b, '.agent-name')),
    recent: (a, b) => parseInt(b.dataset.lastSeen || '0') - parseInt(a.dataset.lastSeen || '0'),
    status: (a, b) => (STATUS_ORDER[textOf(a, '.status-badge')] ?? 9) - (STATUS_ORDER[textOf(b, '.status-badge')] ?? 9),
    tokens: (a, b) => tokensOf(b) - tokensOf(a),
};

/**
 * Creates a span holding a value as text.
 * @param {string} className - Class applied to the span.
 * @param {unknown} value - Value rendered as the span's text.
 * @returns {HTMLSpanElement} The created span.
 */
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
 * @param {Function} openHistoryCallback - Called with the history button when it is activated.
 * @param {Function} [openMenuCallback] - Called with the menu button when it is activated.
 * @returns {HTMLElement} The created card.
 */
export function createCard(data, pyloidIpc, openHistoryCallback, openMenuCallback) {
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
                <button type="button" class="agent-workspace" title="Copy workspace path"></button>
                <div class="agent-session" title="Agent session identifier"></div>
            </div>
            <div class="header-actions">
                <div class="status-badge" title="Current agent state">Idle</div>
                <button type="button" class="menu-icon" title="Agent options">⋮</button>
            </div>
        </div>

        <div class="log-area" title="Real-time operations log (shows last 5 events)">Ready...</div>
        <div class="agent-footer">
            <div class="footer-meta">
                <span class="last-seen-timer" title="Time since last activity">just now</span>
                <div class="metric-badges" title="Recent operation metrics"></div>
            </div>
            <button type="button" class="history-icon" title="View historical operations">🕒</button>
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

    // Concurrent sessions can share an agent and a workspace, so the names
    // carry the whole card identity.
    card.setAttribute('role', 'group');
    card.setAttribute('aria-label', `${agent} session ${sessionId}`);
    const historyButton = card.querySelector('.history-icon');
    historyButton.setAttribute('aria-label', `View history for ${agent} in ${workspace}, session ${sessionId}`);
    historyButton.addEventListener('click', (e) => {
        e.stopPropagation();
        openHistoryCallback(historyButton);
    });

    const menuButton = card.querySelector('.menu-icon');
    menuButton.setAttribute('aria-label', `Options for ${agent} in ${workspace}, session ${sessionId}`);
    menuButton.addEventListener('click', (e) => {
        e.stopPropagation();
        openMenuCallback?.(menuButton);
    });

    // Copy the raw workspace path; never build a shell command from it
    const copyWorkspace = () => {
        pyloidIpc?.DashboardIPC?.copy_to_clipboard(workspace).then((success) => {
            if (success) showCopyFeedback(card);
        });
    };
    // The workspace button is the keyboard route to the whole-card click below.
    card.querySelector('.agent-workspace').addEventListener('click', (e) => {
        e.stopPropagation();
        copyWorkspace();
    });
    card.addEventListener('click', copyWorkspace);

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

    if (details.message) {
        return [segment('Agent:', 'log-completed'), segment(` ${details.message}`)];
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

/**
 * Renders a telemetry event's details as plain text for the history log.
 * @param {object} data - The telemetry data.
 * @returns {string} The joined details text.
 */
function getDetailsString(data) {
    return getDetailsSegments(data).map(segment => segment.text).join('');
}

/**
 * Appends a telemetry event's details to a container, styling each segment.
 * @param {HTMLElement} container - Element the details are appended to.
 * @param {object} data - The telemetry data.
 */
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
 * @returns {{enteredAttention: boolean, message: string}} Whether this update
 *   moved the card into an attention state (Error or Waiting) from one that
 *   wasn't, and the event's log message.
 */
export function updateCard(card, data) {
    const statusBadge = card.querySelector('.status-badge');
    const logArea = card.querySelector('.log-area');
    const metricsArea = card.querySelector('.metric-badges');

    const wasAttention = isAttentionCard(card);
    if (statusBadge) statusBadge.textContent = data.state;
    // Kept separately from the badge so a persisted snapshot reflects the
    // real last state even after checkStaleness overwrites the badge text.
    card.dataset.state = data.state;
    const enteredAttention = ATTENTION_STATES.has(data.state) && !wasAttention;

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
            const badge = textSpan('metric-badge tokens', formatTokens(card.latestTokens));
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
    if (!newLogMessage || newLogMessage === card.lastLogMessage || !logArea) {
        return { enteredAttention, message: newLogMessage || data.state };
    }
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

    return { enteredAttention, message: newLogMessage };
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
        const matches = name.includes(query) || workspace.includes(query);
        card.style.display = matches && card.dataset.hidden !== 'true' ? 'flex' : 'none';
    });
}

/**
 * Sorts the agent grid.
 * @param {string} criteria - The sort criteria.
 * @param {HTMLElement} grid - The agent grid element.
 * @param {boolean} [attentionFirst] - Whether to rank cards needing attention
 *   (Error or Waiting) before the rest, regardless of `criteria`.
 */
export function sortGrid(criteria, grid, attentionFirst = false) {
    const cardsArray = Array.from(grid.children);

    // FIRST: Record positions
    const firstPositions = cardsArray.map(card => {
        const rect = card.getBoundingClientRect();
        return { card, top: rect.top, left: rect.left };
    });

    // LAST: Re-sort DOM
    const compare = Object.hasOwn(CARD_COMPARATORS, criteria) ? CARD_COMPARATORS[criteria] : () => 0;
    const rank = attentionFirst
        ? (a, b) => (Number(isAttentionCard(b)) - Number(isAttentionCard(a))) || compare(a, b)
        : compare;
    cardsArray.sort(rank).forEach(card => grid.appendChild(card));

    if (prefersReducedMotion()) return;

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
 * Tallies the fleet across every tracked card.
 * @param {object} agents - The agents state object.
 * @returns {{total: number, attention: number, stale: number, tokens: number}} The fleet totals.
 */
export function summarizeAgents(agents) {
    let total = 0, attention = 0, stale = 0, tokens = 0;
    for (const card of Object.values(agents)) {
        total++;
        if (card.classList.contains('stale')) stale++;
        if (isAttentionCard(card)) attention++;
        tokens += tokensOf(card);
    }
    return { total, attention, stale, tokens };
}

/**
 * Renders the fleet summary badges (total, needs attention, stale, tokens).
 * @param {HTMLElement | null} container - The summary bar element.
 * @param {object} agents - The agents state object.
 */
export function renderSummary(container, agents) {
    if (!container) return;
    const { total, attention, stale, tokens } = summarizeAgents(agents);

    const badge = (className, text, title) => {
        const span = textSpan(className, text);
        span.title = title;
        return span;
    };

    container.replaceChildren(
        badge('summary-badge', `${total} agent${total === 1 ? '' : 's'}`, 'Total agent cards'),
        badge(`summary-badge${attention > 0 ? ' summary-attention' : ''}`, `${attention} need${attention === 1 ? 's' : ''} attention`, 'Cards in Error or Waiting state'),
        badge('summary-badge', `${stale} stale`, 'Cards past the stale threshold'),
        badge('summary-badge', `${formatTokens(tokens)} tokens`, 'Combined tokens across active operations'),
    );
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
        if (historyModal) openDialog(historyModal);
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
