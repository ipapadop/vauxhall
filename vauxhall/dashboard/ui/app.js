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
    
    // Tracks which agent is currently being viewed in the modal for live updates
    let currentHistoryKey = null;

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

    if (closeBtn) {
        closeBtn.onclick = () => {
            closeHistoryModal();
            currentHistoryKey = null;
        };
    }
    
    // Close modal on background click
    window.onclick = (event) => {
        if (event.target == modal) {
            closeHistoryModal();
            currentHistoryKey = null;
        }
    };

    // Initialize IPC with Python backend
    let staleThresholdMs = 120000;
    try {
        if (!window.pyloid) return;

        initIPC({
            onAgentUpdate: (data) => {
                const key = `${data.agent}:${data.workspace}`;
                let card = agents[key];

                if (!card) {
                    card = createCard(data, window.ipc, (key) => {
                        currentHistoryKey = key; // Lock modal to this agent
                        openHistoryModal(key, agents);
                    });
                    agents[key] = card;
                    grid.appendChild(card);
                }

                // Global state management
                updateAgentHistory(card, data);
                updateLastSeen(card);
                
                // UI updates
                updateCard(card, data);

                // Push live updates to the history modal if it's viewing this agent
                if (currentHistoryKey === key) {
                    openHistoryModal(key, agents, true); // true = silent update
                }

                // Re-apply filter and sort to keep view consistent
                if (searchInput && searchInput.value) {
                    filterGrid(searchInput.value.toLowerCase(), agents);
                }
                if (sortSelect && sortSelect.value) {
                    sortGrid(sortSelect.value, grid);
                }
            },
            onReady: () => {
                if (status) status.innerText = "Connected to Agent Fleet";

                // Fetch stale threshold from settings
                if (window.ipc && window.ipc.DashboardIPC) {
                    window.ipc.DashboardIPC.get_stale_threshold().then(seconds => {
                        staleThresholdMs = seconds * 1000;
                        console.log(`Stale threshold set to ${staleThresholdMs}ms`);
                    }).catch(err => {
                        console.error("Failed to fetch stale threshold:", err);
                    });
                }
            },
            onError: (err) => {
                console.error("IPC Error:", err);
                if (status) status.innerText = err;
            }
        });

        // Start staleness check every 10 seconds
        setInterval(() => checkStaleness(agents, staleThresholdMs), 10000);

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
