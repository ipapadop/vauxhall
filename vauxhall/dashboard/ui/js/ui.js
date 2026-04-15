/**
 * SPDX-License-Identifier: MIT
 */

/**
 * @file ui.js
 * @description Handles DOM manipulation, card creation, and updates.
 */

import { updateTokenHistory } from './state.js';

/**
 * Generates an SVG polyline points string for a sparkline.
 * @param {number[]} history - The history of values.
 * @returns {string} The points string for a polyline.
 */
export function generateSparklinePath(history) {
    if (!history || history.length < 2) return "";
    
    const width = 100;
    const height = 20;
    const max = Math.max(...history);
    const min = Math.min(...history);
    const range = (max - min) || 1;
    
    return history.map((val, i) => {
        const x = (i / (history.length - 1)) * width;
        const y = height - ((val - min) / range) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
}

/**
 * Creates an agent card element.
 * @param {Object} data - Initial telemetry data.
 * @param {Object} pyloidIpc - Pyloid IPC bridge.
 * @param {Function} openHistoryCallback - Function to call when history icon is clicked.
 * @returns {HTMLElement} The created card.
 */
export function createCard(data, pyloidIpc, openHistoryCallback) {
    // Guess environment if not provided
    const env = data.env || (data.workspace.startsWith('/home') || data.workspace.match(/^[A-Z]:\\/) ? 'local' : 'remote');
    
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.title = "Click to copy workspace path";
    card.innerHTML = `
        <div class="agent-header">
            <div class="agent-info">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="env-badge env-${env}" title="Execution environment">${env}</span>
                    <div class="agent-name" title="Agent name">${data.agent}</div>
                </div>
                <div class="agent-workspace" title="Current workspace path">${data.workspace}</div>
            </div>
            <div class="status-badge" title="Current agent state">Idle</div>
        </div>
        <div class="stats-row">
            <svg class="sparkline" viewBox="0 0 100 20" preserveAspectRatio="none" title="Token usage trend over the last 20 operations">
                <polyline points="" fill="none" stroke="var(--accent-color)" stroke-width="1" vector-effect="non-scaling-stroke"></polyline>
            </svg>
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
    
    // Setup History Modal Trigger
    card.querySelector('.history-icon').addEventListener('click', (e) => {
        e.stopPropagation();
        const key = `${data.agent}:${data.workspace}`;
        openHistoryCallback(key);
    });
    
    // Setup Workspace Copy Trigger
    card.addEventListener('click', () => {
        pyloidIpc.DashboardIPC.copy_to_clipboard(`cd ${data.workspace}`).then(success => {
            if (success) {
                showCopyFeedback(card);
            }
        });
    });
    
    return card;
}

/**
 * Formats the details object into a human-readable action string.
 * @param {Object} details - The telemetry details.
 * @returns {string} A formatted string describing the action.
 */
function getDetailsString(details) {
    if (!details) return "";
    if (details.tool) {
        return `Running: ${details.tool}${details.cmd ? ' ' + details.cmd : ''}`;
    } else if (details.prompt) {
        return `Prompt: ${details.prompt}`;
    } else if (details.error) {
        return `Error: ${details.error}`;
    } else if (details.status) {
        return details.status;
    }
    return "";
}

/**
 * Updates an agent card with new telemetry.
 * Handles state styles, metrics, sparklines, and the 5-event rolling log.
 */
export function updateCard(card, data) {
    const statusBadge = card.querySelector('.status-badge');
    const logArea = card.querySelector('.log-area');
    const metricsArea = card.querySelector('.metric-badges');
    
    statusBadge.textContent = data.state;
    
    // Update color-coded state classes
    card.classList.remove('error', 'waiting', 'working');
    if (data.state === 'Error') {
        card.classList.add('error');
    } else if (data.state === 'Waiting' || data.state === 'Waiting for Input' || data.state === 'Input Required') {
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

    // Accumulate metrics
    if (details.tokens) card.latestTokens = details.tokens;
    if (details.duration) card.latestDuration = details.duration;

    // Update Token History & SVG Sparkline
    updateTokenHistory(card, details.tokens);
    const polyline = card.querySelector('.sparkline polyline');
    if (polyline && card.tokenHistory) {
        polyline.setAttribute('points', generateSparklinePath(card.tokenHistory));
    }

    // Update Footer Metric Badges
    if (metricsArea) {
        metricsArea.innerHTML = '';
        if (card.latestTokens) {
            const t = card.latestTokens > 1000 ? (card.latestTokens/1000).toFixed(1) + 'k' : card.latestTokens;
            metricsArea.innerHTML += `<span class="metric-badge tokens" data-value="${card.latestTokens}" title="Tokens used in last operation">${t}</span>`;
        }
        if (card.latestDuration) {
            metricsArea.innerHTML += `<span class="metric-badge" title="Duration of last operation">${card.latestDuration}s</span>`;
        }
    }

    // Update Rolling Activity Log (last 5 entries)
    const newLogMessage = getDetailsString(details);

    if (newLogMessage && newLogMessage !== card.lastLogMessage) {
        card.lastLogMessage = newLogMessage;
        
        const time = new Date().toLocaleTimeString([], { 
            hour12: false, 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        });

        if (logArea.textContent === "Ready...") {
            logArea.innerHTML = "";
        }

        const logLine = document.createElement('div');
        logLine.className = 'log-line';
        logLine.innerHTML = `<span style="color: var(--text-dim)">[${time}]</span> `;
        logLine.appendChild(document.createTextNode(newLogMessage));
        
        logArea.appendChild(logLine);

        // Enforce 5-event limit for the card view
        while (logArea.children.length > 5) {
            logArea.removeChild(logArea.firstElementChild);
        }
    }
}

/**
 * Shows "Copied!" feedback on a card.
 */
function showCopyFeedback(card) {
    card.classList.add('copied');
    setTimeout(() => {
        card.classList.remove('copied');
    }, 2000);
}

/**
 * Filters the agent grid.
 */
export function filterGrid(query, agents) {
    Object.values(agents).forEach(card => {
        const name = card.querySelector('.agent-name').textContent.toLowerCase();
        const workspace = card.querySelector('.agent-workspace').textContent.toLowerCase();
        if (name.includes(query) || workspace.includes(query)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * Sorts the agent grid.
 */
export function sortGrid(criteria, grid) {
    const cardsArray = Array.from(grid.children);

    const sorted = cardsArray.sort((a, b) => {
        if (criteria === 'name') {
            const nameA = a.querySelector('.agent-name').textContent;
            const nameB = b.querySelector('.agent-name').textContent;
            return nameA.localeCompare(nameB);
        } else if (criteria === 'recent') {
            return parseInt(b.dataset.lastSeen) - parseInt(a.dataset.lastSeen);
        } else if (criteria === 'status') {
            const statusOrder = { 'Error': 0, 'Waiting': 1, 'Input Required': 1, 'Waiting for Input': 1, 'Acting': 2, 'Thinking': 2, 'Idle': 3, 'STALE': 4 };
            const statusA = a.querySelector('.status-badge').textContent;
            const statusB = b.querySelector('.status-badge').textContent;
            return (statusOrder[statusA] ?? 9) - (statusOrder[statusB] ?? 9);
        } else if (criteria === 'tokens') {
            const tokensA = parseInt(a.querySelector('.metric-badge.tokens')?.dataset.value || 0);
            const tokensB = parseInt(b.querySelector('.metric-badge.tokens')?.dataset.value || 0);
            return tokensB - tokensA;
        }
        return 0;
    });

    grid.innerHTML = '';
    sorted.forEach(card => grid.appendChild(card));
}

/**
 * Checks for stale agents and updates the last seen timer.
 */
export function checkStaleness(agents, staleThresholdMs = 120000) {
    const now = Date.now();

    Object.values(agents).forEach(card => {
        const lastSeen = parseInt(card.dataset.lastSeen);
        const diff = now - lastSeen;
        
        // Update timer text
        const timer = card.querySelector('.last-seen-timer');
        if (timer) {
            if (diff < 60000) {
                timer.textContent = 'just now';
            } else {
                const minutes = Math.floor(diff / 60000);
                timer.textContent = `${minutes}m ago`;
            }
        }

        if (diff > staleThresholdMs) {
            card.classList.add('stale');
            const statusBadge = card.querySelector('.status-badge');
            if (statusBadge && statusBadge.textContent !== 'STALE') {
                statusBadge.textContent = 'STALE';
            }
        } else {
            card.classList.remove('stale');
        }
    });
}

let isInteractingWithModal = false;

/**
 * Populates and opens the history modal.
 * Supports real-time updates and resizable behavior.
 * 
 * @param {string} agentKey - Unique key for the agent.
 * @param {Object} agents - Global agents state object.
 * @param {boolean} isSilent - If true, updates content without forcing focus or jumping to bottom (unless already there).
 */
export function openHistoryModal(agentKey, agents, isSilent = false) {
    const card = agents[agentKey];
    if (!card || !card.history) return;

    if (!isSilent) {
        document.getElementById('modal-agent-name').textContent = `History: ${agentKey}`;
    }

    const body = document.getElementById('modal-history-body');
    
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
        const matchesSearch = getDetailsString(item.details).toLowerCase().includes(searchTerm);
        const matchesState = stateFilter === 'ALL' || item.state === stateFilter || (stateFilter === 'Waiting' && item.state === 'Waiting for Input');
        return matchesSearch && matchesState;
    });

    // Re-render timeline items
    body.innerHTML = filteredHistory.map(item => `
        <div class="history-item">
            <span class="history-time">${item.time}</span>
            <span class="history-state">${item.state}</span>
            <span class="history-details">${getDetailsString(item.details)}</span>
        </div>
    `).reverse().join(''); // Chronological order (oldest top, newest bottom)

    const isInteracting = body.matches(':hover') || isInteractingWithModal;

    if (!isSilent) {
        // Initial open: Show modal and jump to latest event
        document.getElementById('history-modal').style.display = "block";
        body.scrollTop = body.scrollHeight;
    } else if (isAtBottom && !isInteracting) {
        // Live update: Only follow tail if user was already at the bottom and isn't hovering
        body.scrollTop = body.scrollHeight;
    } else {
        // Freeze mode: Restore scroll position to prevent jumping during innerHTML refresh
        body.scrollTop = oldScrollTop;
    }
}

/**
 * Closes the history modal.
 */
export function closeHistoryModal() {
    document.getElementById('history-modal').style.display = "none";
}
