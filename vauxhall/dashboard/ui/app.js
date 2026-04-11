/**
 * @file app.js
 * @description Main entry point for the Vauxhall Dashboard frontend.
 */

import { agents, updateAgentHistory, updateLastSeen, clearAgents, removeAgent } from './js/state.js';
import { createCard, updateCard, filterGrid, sortGrid, checkStaleness, openHistoryModal, closeHistoryModal } from './js/ui.js';
import { initIPC } from './js/ipc.js';

function init() {
    console.log("Vauxhall Dashboard Initialized");
    const status = document.getElementById('js-status');
    const grid = document.getElementById('agent-grid');
    
    // UI Element References
    const clearBtn = document.getElementById('clear-btn');
    const clearStaleBtn = document.getElementById('clear-stale-btn');
    const searchInput = document.getElementById('search-input');
    const sortSelect = document.getElementById('sort-select');
    const closeBtn = document.querySelector('.close-btn');
    const modal = document.getElementById('history-modal');

    // Setup Event Listeners
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            grid.innerHTML = '';
            clearAgents();
        });
    }

    if (clearStaleBtn) {
        clearStaleBtn.addEventListener('click', () => {
            for (const key in agents) {
                const card = agents[key];
                if (card.classList.contains('stale')) {
                    card.remove();
                    removeAgent(key);
                }
            }
        });
    }

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            filterGrid(e.target.value.toLowerCase(), agents);
        });
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            sortGrid(e.target.value, grid);
        });
    }

    if (closeBtn) closeBtn.onclick = closeHistoryModal;
    window.onclick = (event) => {
        if (event.target == modal) closeHistoryModal();
    };

    // Initialize IPC
    try {
        if (!window.pyloid) return;

        initIPC({
            onAgentUpdate: (data) => {
                const key = `${data.agent}:${data.workspace}`;
                let card = agents[key];

                if (!card) {
                    card = createCard(data, window.ipc, (key) => openHistoryModal(key, agents));
                    agents[key] = card;
                    grid.appendChild(card);
                }

                updateAgentHistory(card, data);
                updateLastSeen(card);
                updateCard(card, data);

                // Re-apply filter and sort
                if (searchInput && searchInput.value) {
                    filterGrid(searchInput.value.toLowerCase(), agents);
                }
                if (sortSelect && sortSelect.value) {
                    sortGrid(sortSelect.value, grid);
                }
            },
            onReady: () => {
                if (status) status.innerText = "Connected to Agent Fleet";
            },
            onError: (err) => {
                console.error("IPC Error:", err);
                if (status) status.innerText = err;
            }
        });

        // Start staleness check every 10 seconds
        setInterval(() => checkStaleness(agents), 10000);

    } catch (err) {
        console.error("Initialization error:", err);
    }
}

// Entry Point
if (window.pyloid) {
    init();
} else {
    window.addEventListener('pyloidReady', init);
    
    // Fallback: Check every 100ms for 2 seconds
    let checks = 0;
    const interval = setInterval(() => {
        checks++;
        if (window.pyloid) {
            init();
            clearInterval(interval);
        } else if (checks > 20) {
            clearInterval(interval);
            console.error("Pyloid not found after 2 seconds");
        }
    }, 100);
}
