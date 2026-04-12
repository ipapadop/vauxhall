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
    card.innerHTML = `
        <div class="agent-header">
            <div class="agent-info">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="env-badge env-${env}">${env}</span>
                    <div class="agent-name">${data.agent}</div>
                    <div class="metric-badges"></div>
                    <span class="history-icon" title="View History" style="cursor: pointer; font-size: 0.8em; margin-left: 5px;">🕒</span>
                </div>
                <div class="agent-workspace">${data.workspace}</div>
                <div class="last-seen-timer" style="font-size: 0.7em; color: var(--text-dim); margin-top: 2px;">just now</div>
            </div>
            <div class="status-badge">Idle</div>
        </div>
        <div class="stats-row">
            <svg class="sparkline" viewBox="0 0 100 20" preserveAspectRatio="none">
                <polyline points="" fill="none" stroke="var(--accent-color)" stroke-width="1" vector-effect="non-scaling-stroke"></polyline>
            </svg>
        </div>
        <div class="log-area">Ready...</div>
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
            metricsArea.innerHTML += `<span class="metric-badge tokens" data-value="${details.tokens}">${t}</span>`;
        }
        if (details.duration) {
            metricsArea.innerHTML += `<span class="metric-badge">${details.duration}s</span>`;
        }
    }

    // Update Log Area
    let newLogMessage = "";
    if (details.tool) {
        newLogMessage = `Running: ${details.tool}${details.cmd ? ' ' + details.cmd : ''}`;
    } else if (details.prompt) {
        newLogMessage = `Prompt: ${details.prompt}`;
    }

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

        // Truncate to 50 lines using DOM elements
        while (logArea.children.length > 50) {
            logArea.removeChild(logArea.firstChild);
        }
        
        logArea.scrollTop = logArea.scrollHeight;
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

/**
 * Populates and opens the history modal.
 */
export function openHistoryModal(agentKey, agents) {
    const card = agents[agentKey];
    if (!card || !card.history) return;

    document.getElementById('modal-agent-name').textContent = `History: ${agentKey}`;
    const body = document.getElementById('modal-history-body');
    body.innerHTML = card.history.map(item => `
        <div class="history-item">
            <span class="history-time">${item.time}</span>
            <span class="history-state">${item.state}</span>
            <span class="history-details">${item.details.tool || item.details.prompt || item.details.error || ''}</span>
        </div>
    `).join('');

    document.getElementById('history-modal').style.display = "block";
    
    // Auto-scroll to bottom
    body.scrollTop = body.scrollHeight;
}

/**
 * Closes the history modal.
 */
export function closeHistoryModal() {
    document.getElementById('history-modal').style.display = "none";
}
