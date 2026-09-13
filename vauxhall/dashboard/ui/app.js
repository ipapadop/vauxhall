/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file app.js
 * @description Main entry point for the Vauxhall Dashboard frontend.
 */

import { agentKey, agents, updateAgentHistory, updateLastSeen, clearAgents, removeAgent, ensureAgentCapacity } from './js/state.js';
import { createCard, updateCard, filterGrid, sortGrid, checkStaleness, openHistoryModal, closeHistoryModal } from './js/ui.js';
import { initIPC } from './js/ipc.js';

async function init() {
    console.log("Vauxhall Dashboard Initialized");
    const status = document.getElementById('js-status');
    const grid = document.getElementById('agent-grid');

    if (!grid) return;

    const logoLink = document.getElementById('logo-link');
    const searchInput = document.getElementById('search-input');
    const sortSelect = document.getElementById('sort-select');
    const modal = document.getElementById('history-modal');

    // Theme Management
    document.documentElement.setAttribute('data-theme', localStorage.getItem('vauxhall-theme') || 'dark');
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
        const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('vauxhall-theme', newTheme);
    });

    logoLink?.addEventListener('click', (e) => {
        e.preventDefault();
        const url = logoLink.getAttribute('href');
        if (url) window.ipc?.DashboardIPC?.open_url(url);
    });

    // Tracks which agent is currently being viewed in the modal for live updates
    let currentHistoryKey = null;
    const closeModal = () => {
        closeHistoryModal();
        currentHistoryKey = null;
    };
    const refreshModal = () => {
        if (currentHistoryKey) openHistoryModal(currentHistoryKey, agents, true);
    };

    document.getElementById('clear-btn')?.addEventListener('click', () => {
        grid.innerHTML = '';
        clearAgents();
    });

    document.getElementById('clear-stale-btn')?.addEventListener('click', () => {
        for (const [key, card] of Object.entries(agents)) {
            if (card.classList.contains('stale')) {
                card.remove();
                removeAgent(key);
            }
        }
    });

    searchInput?.addEventListener('input', (e) => filterGrid(e.target.value.toLowerCase(), agents));
    sortSelect?.addEventListener('change', (e) => sortGrid(e.target.value, grid));
    document.querySelector('.close-btn')?.addEventListener('click', closeModal);
    document.getElementById('modal-search')?.addEventListener('input', refreshModal);
    document.getElementById('modal-state-filter')?.addEventListener('change', refreshModal);

    // Close modal on background click
    window.onclick = (event) => {
        if (event.target === modal) closeModal();
    };

    // Initialize IPC with Python backend
    let staleThresholdMs = 120000;
    let maxActiveAgents = 100;
    try {
        if (!window.pyloid) return;

        if (window.ipc?.DashboardIPC) {
            try {
                maxActiveAgents = await window.ipc.DashboardIPC.get_max_active_agents();
                console.log(`Maximum active agents set to ${maxActiveAgents}`);
            } catch (err) {
                console.error("Failed to fetch maximum active agents:", err);
            }
        }

        initIPC({
            onAgentUpdate: (data) => {
                const key = agentKey(data);
                let card = agents[key];

                if (!card) {
                    if (ensureAgentCapacity(maxActiveAgents) === currentHistoryKey) closeModal();
                    card = createCard(data, window.ipc, () => {
                        currentHistoryKey = key; // Lock modal to this agent
                        openHistoryModal(key, agents);
                    });
                    agents[key] = card;
                    grid.appendChild(card);
                }

                updateAgentHistory(card, data);
                updateLastSeen(card);
                updateCard(card, data);

                // Push live updates to the history modal if it's viewing this agent
                if (currentHistoryKey === key) openHistoryModal(key, agents, true);

                // Re-apply filter and sort to keep view consistent
                if (searchInput?.value) filterGrid(searchInput.value.toLowerCase(), agents);
                if (sortSelect?.value) sortGrid(sortSelect.value, grid);
            },
            onStatusUpdate: (msg) => {
                if (status) status.innerText = msg;
            },
            onReady: () => {
                if (status) status.innerText = "Connected to Agent Fleet";

                // Fetch stale threshold from settings
                window.ipc?.DashboardIPC?.get_stale_threshold().then(seconds => {
                    staleThresholdMs = seconds * 1000;
                    console.log(`Stale threshold set to ${staleThresholdMs}ms`);
                }).catch(err => {
                    console.error("Failed to fetch stale threshold:", err);
                });
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
