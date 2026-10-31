/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file card.js
 * @description Builds agent cards and describes telemetry events.
 */

import { element } from './dom.js';
import { cardIdentity } from './state.js';

export const WAITING_STATES = new Set(['Waiting for Input', 'Input Required']);

// States that need a human: an active error, or a prompt/permission the agent is blocked on.
const ATTENTION_STATES = new Set([...WAITING_STATES, 'Error']);

/**
 * Returns whether a value is a finite number above zero.
 * @param {unknown} value - The candidate number.
 * @returns {boolean} Whether the value is usable as a positive metric.
 */
export const isPositiveNumber = (value) => typeof value === 'number' && Number.isFinite(value) && value > 0;
/**
 * Returns a card's token count, or zero when it has no token badge.
 * @param {HTMLElement} card - The agent card.
 * @returns {number} The token count.
 */
export const tokensOf = (card) => parseInt(card.querySelector('.metric-badge.tokens')?.dataset.value || '0');
/**
 * Returns whether a card is in a state that needs a human. Reads the
 * 'error'/'waiting' state classes rather than the status badge text, since
 * checkStaleness overwrites the badge to "STALE" but leaves those classes
 * alone — a card blocked long enough to go stale still needs attention.
 * @param {HTMLElement} card - The agent card.
 * @returns {boolean} Whether the card needs attention.
 */
export const isAttentionCard = (card) => card.classList.contains('error') || card.classList.contains('waiting');
/**
 * Formats a token count, abbreviating counts over 1000.
 * @param {number} count - The token count.
 * @returns {string} The formatted count.
 */
export const formatTokens = (count) => count > 1000 ? `${(count / 1000).toFixed(1)}k` : String(count);

/**
 * Returns the color category of a state, shared by cards and history rows.
 * @param {string} state - The telemetry state.
 * @returns {string} One of `error`, `waiting`, `acting`, `thinking`, or `idle`.
 */
export function stateCategory(state) {
    if (state === 'Error') return 'error';
    if (WAITING_STATES.has(state)) return 'waiting';
    if (state === 'Acting') return 'acting';
    if (state === 'Thinking') return 'thinking';
    return 'idle';
}

// A card colors acting and thinking alike, and idle not at all.
const CARD_CLASSES = { error: 'error', waiting: 'waiting', acting: 'working', thinking: 'working' };

/**
 * Creates an agent card element.
 * @param {object} data - Initial telemetry data.
 * @param {Function} openPaneCallback - Called with the workspace button, the
 *   control to focus again, when the card is clicked or that button activated.
 * @param {Function} [openMenuCallback] - Called with the menu button when it is activated.
 * @returns {HTMLElement} The created card.
 */
export function createCard(data, openPaneCallback, openMenuCallback) {
    const agent = String(data.agent ?? '');
    const sessionId = String(data.session_id ?? '');

    const card = document.createElement('div');
    card.className = 'agent-card';
    card.title = "Click to open the activity timeline";
    card.innerHTML = `
        <div class="agent-header">
            <div class="agent-info">
                <div class="agent-title">
                    <span class="env-badge" title="Execution environment"></span>
                    <div class="agent-name" title="Agent name"></div>
                </div>
                <button type="button" class="agent-workspace" title="Open the activity timeline"></button>
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
        </div>
    `;

    card.querySelector('.agent-name').textContent = agent;
    const sessionElement = card.querySelector('.agent-session');
    sessionElement.textContent = `Session: ${sessionId}`;
    sessionElement.title = sessionId;
    card.history = [];

    // Concurrent sessions can share an agent and a workspace, so the names
    // carry the whole card identity.
    card.setAttribute('role', 'group');
    card.setAttribute('aria-label', `${agent} session ${sessionId}`);
    const menuButton = card.querySelector('.menu-icon');
    menuButton.addEventListener('click', (e) => {
        e.stopPropagation();
        openMenuCallback?.(menuButton);
    });

    // The workspace button is the keyboard route to the whole-card click; its
    // click bubbles here, and focus returns to it when the pane closes.
    const workspaceButton = card.querySelector('.agent-workspace');
    card.addEventListener('click', () => openPaneCallback(workspaceButton));
    setWorkspace(card, data);

    return card;
}

/**
 * Shows a card's workspace and the environment and control names derived
 * from it. A session's workspace is its current directory, so it can change.
 * @param {HTMLElement} card - The agent card element.
 * @param {object} data - Telemetry data naming the workspace and, optionally, env.
 */
function setWorkspace(card, data) {
    const workspace = String(data.workspace ?? '');
    const envBadge = card.querySelector('.env-badge');
    // The environment belongs to the session, not the directory: an event
    // without env keeps the card's, and the path is a guess for the first.
    const configuredEnv = data.env === 'local' || data.env === 'remote' ? data.env : null;
    const env = configuredEnv || envBadge.textContent
        || (workspace.startsWith('/home') || /^[A-Z]:\\/i.test(workspace) ? 'local' : 'remote');
    const workspaceButton = card.querySelector('.agent-workspace');
    // Rewriting unchanged text would drop a selection in it on every event.
    if (workspaceButton.textContent === workspace && envBadge.textContent === env) return;
    envBadge.classList.remove('env-local', 'env-remote');
    envBadge.classList.add(`env-${env}`);
    envBadge.textContent = env;

    const { agent, session_id: sessionId } = cardIdentity(card);
    workspaceButton.textContent = workspace;
    workspaceButton.setAttribute('aria-label', `Open activity for ${agent} in ${workspace}, session ${sessionId}`);
    card.querySelector('.menu-icon').setAttribute('aria-label', `Options for ${agent} in ${workspace}, session ${sessionId}`);
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
export function getDetailsString(data) {
    return getDetailsSegments(data).map(segment => segment.text).join('');
}

/**
 * Appends a telemetry event's details to a container, styling each segment.
 * @param {HTMLElement} container - Element the details are appended to.
 * @param {object} data - The telemetry data.
 */
export function appendDetails(container, data) {
    getDetailsSegments(data).forEach(({ text, className }) => {
        container.appendChild(className ? element('span', className, text) : document.createTextNode(text));
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
    setWorkspace(card, data);
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
    const cardClass = CARD_CLASSES[stateCategory(data.state)];
    if (cardClass) card.classList.add(cardClass);

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
            const badge = element('span', 'metric-badge tokens', formatTokens(card.latestTokens));
            badge.dataset.value = String(card.latestTokens);
            badge.title = 'Tokens used in last operation';
            metricsArea.appendChild(badge);
        }
        if (card.latestDuration) {
            const badge = element('span', 'metric-badge', `${card.latestDuration}s`);
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
 * Copies a raw workspace path, never a shell command built from it.
 * @param {any} ipc - The DashboardIPC bridge.
 * @param {string} workspace - The path to copy.
 * @returns {Promise<string>} `Copied!`, or `Copy failed` when the bridge is
 *   missing, refuses, or throws.
 */
export async function copyWorkspacePath(ipc, workspace) {
    let copied = false;
    try {
        copied = Boolean(await ipc?.copy_to_clipboard?.(workspace));
    } catch (err) {
        console.error('Failed to copy workspace path:', err);
    }
    return copied ? 'Copied!' : 'Copy failed';
}
