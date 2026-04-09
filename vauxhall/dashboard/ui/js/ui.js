/**
 * @file ui.js
 * @description Handles DOM manipulation, card creation, and updates.
 */

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
    if (details.tool) {
        logArea.textContent = `Running: ${details.tool}\n${details.cmd || ''}`;
    } else if (details.prompt) {
        logArea.textContent = `Prompt: ${details.prompt}`;
    } else {
        logArea.textContent = "Ready...";
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
export function checkStaleness(agents) {
    const now = Date.now();
    const staleThreshold = 120000; // 2 minutes

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

        if (diff > staleThreshold) {
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
