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
 */
export function createCard(data, pyloidIpc, openHistoryCallback) {
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
        <div class="log-area" title="Real-time operations log (scrolls automatically unless hovered)">Ready...</div>
        <div class="agent-footer">
            <div class="footer-meta">
                <span class="last-seen-timer" title="Time since last activity">just now</span>
                <div class="metric-badges" title="Recent operation metrics"></div>
            </div>
            <span class="history-icon" title="View historical operations">🕒</span>
        </div>
    `;
    
    // History Click
    card.querySelector('.history-icon').addEventListener('click', (e) => {
        e.stopPropagation();
        const key = `${data.agent}:${data.workspace}`;
        openHistoryCallback(key);
    });
    
    // Copy Click
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
 */
export function updateCard(card, data) {
    const statusBadge = card.querySelector('.status-badge');
    const logArea = card.querySelector('.log-area');
    const metricsArea = card.querySelector('.metric-badges');
    
    statusBadge.textContent = data.state;
    
    // Update State Classes
    card.classList.remove('error', 'waiting', 'working');
    if (data.state === 'Error') {
        card.classList.add('error');
    } else if (data.state === 'Waiting' || data.state === 'Waiting for Input' || data.state === 'Input Required') {
        card.classList.add('waiting');
    } else if (data.state === 'Acting' || data.state === 'Thinking') {
        card.classList.add('working');
    }

    // Update Metrics
    const details = data.details || {};
    
    // Update Token History & Sparkline
    updateTokenHistory(card, details.tokens);
    const polyline = card.querySelector('.sparkline polyline');
    if (polyline && card.tokenHistory) {
        polyline.setAttribute('points', generateSparklinePath(card.tokenHistory));
    }

    if (metricsArea) {
        metricsArea.innerHTML = '';
        if (details.tokens) {
            const t = details.tokens > 1000 ? (details.tokens/1000).toFixed(1) + 'k' : details.tokens;
            metricsArea.innerHTML += `<span class="metric-badge tokens" data-value="${details.tokens}" title="Tokens used in last operation">${t}</span>`;
        }
        if (details.duration) {
            metricsArea.innerHTML += `<span class="metric-badge" title="Duration of last operation">${details.duration}s</span>`;
        }
    }

    // Update Log Area
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

        // Truncate to 5 events (last 5)
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
 */
export function openHistoryModal(agentKey, agents, isSilent = false) {
    const card = agents[agentKey];
    if (!card || !card.history) return;

    if (!isSilent) {
        document.getElementById('modal-agent-name').textContent = `History: ${agentKey}`;
    }

    const body = document.getElementById('modal-history-body');
    
    // Capture scroll state BEFORE updating content
    const isAtBottom = body.scrollHeight - body.scrollTop <= body.clientHeight + 50;
    const oldScrollTop = body.scrollTop;

    // Set up interaction listeners once
    if (!body.hasListeners) {
        body.addEventListener('pointerdown', () => { isInteractingWithModal = true; });
        window.addEventListener('pointerup', () => { isInteractingWithModal = false; });
        window.addEventListener('pointercancel', () => { isInteractingWithModal = false; });
        body.hasListeners = true;
    }

    body.innerHTML = card.history.map(item => `
        <div class="history-item">
            <span class="history-time">${item.time}</span>
            <span class="history-state">${item.state}</span>
            <span class="history-details">${getDetailsString(item.details)}</span>
        </div>
    `).reverse().join(''); // Show in chronological order

    const isInteracting = body.matches(':hover') || isInteractingWithModal;

    if (!isSilent) {
        document.getElementById('history-modal').style.display = "block";
        body.scrollTop = body.scrollHeight;
    } else if (isAtBottom && !isInteracting) {
        body.scrollTop = body.scrollHeight;
    } else {
        // Freeze mode: Restore previous scroll position
        // This is necessary because innerHTML assignment resets scrollTop to 0.
        body.scrollTop = oldScrollTop;
    }
}

/**
 * Closes the history modal.
 */
export function closeHistoryModal() {
    document.getElementById('history-modal').style.display = "none";
}
