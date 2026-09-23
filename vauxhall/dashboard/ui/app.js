/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file app.js
 * @description Main entry point for the Vauxhall Dashboard frontend.
 */

import { agentKey, agents, updateAgentHistory, updateLastSeen, clearAgents, removeAgent, ensureAgentCapacity, evictAgents, isHidden, setHidden } from './js/state.js';
import { createCard, updateCard, filterGrid, sortGrid, checkStaleness, openHistoryModal, closeHistoryModal } from './js/ui.js';
import { closeDialog, openDialog } from './js/dialog.js';
import { saveDenylist } from './js/denylist.js';
import { initIPC } from './js/ipc.js';
import { initSettings } from './js/settings.js';
import { cacheTheme, cachedTheme, createPreferenceSaver, isTheme, restorePreferences } from './js/preferences.js';

/**
 * Builds the dashboard, restores preferences, and starts the telemetry feed.
 */
async function init() {
    console.log("Vauxhall Dashboard Initialized");
    const status = document.getElementById('js-status');
    const grid = document.getElementById('agent-grid');

    if (!grid) return;

    const logoLink = document.getElementById('logo-link');
    const searchInput = document.getElementById('search-input');
    const sortSelect = document.getElementById('sort-select');
    const modal = document.getElementById('history-modal');
    const historyFilter = document.getElementById('modal-state-filter');

    // Theme and view preferences. Saving starts once the Python bridge is available,
    // and preferences changed before the saved ones load are not overwritten.
    let preferences = { save: () => {}, flush: () => {} };
    const changedPreferences = new Set();
    const changePreference = (key, value) => {
        changedPreferences.add(key);
        preferences.save({ [key]: value });
    };
    const applyTheme = (theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        cacheTheme(theme);
    };
    const initialTheme = cachedTheme();
    document.documentElement.setAttribute('data-theme', isTheme(initialTheme) ? initialTheme : 'dark');
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
        const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
        changePreference('theme', newTheme);
    });

    logoLink?.addEventListener('click', (e) => {
        e.preventDefault();
        const url = logoLink.getAttribute('href');
        if (url) window.ipc?.DashboardIPC?.open_url(url);
    });

    // Tracks which agent is currently being viewed in the modal for live updates
    let currentHistoryKey = null;
    let historyOpener = null;
    const closeModal = () => closeHistoryModal();
    // The close button, the backdrop, and Escape all end in the dialog's close
    // event, so the view state and the focus return are restored in one place.
    // An opener evicted while the dialog was open hands focus to the grid.
    modal?.addEventListener('close', () => {
        currentHistoryKey = null;
        (historyOpener?.isConnected ? historyOpener : grid).focus?.();
        historyOpener = null;
    });
    const refreshModal = () => {
        if (currentHistoryKey) openHistoryModal(currentHistoryKey, agents, true);
    };

    // Tracks which agent card the options menu is currently acting on.
    const cardMenuModal = document.getElementById('card-menu-modal');
    let currentMenuKey = null;
    let menuOpener = null;
    const closeMenu = () => closeDialog(cardMenuModal);
    cardMenuModal?.addEventListener('close', () => {
        currentMenuKey = null;
        (menuOpener?.isConnected ? menuOpener : grid).focus?.();
        menuOpener = null;
    });
    document.getElementById('card-menu-close')?.addEventListener('click', closeMenu);
    document.getElementById('card-menu-hide')?.addEventListener('click', () => {
        const card = agents[currentMenuKey];
        if (card) setHidden(card, true);
        closeMenu();
    });
    document.getElementById('card-menu-denylist')?.addEventListener('click', async () => {
        const card = agents[currentMenuKey];
        const agentName = card?.querySelector('.agent-name')?.textContent;
        closeMenu();
        if (!agentName || !window.ipc?.DashboardIPC) return;
        try {
            const descriptor = JSON.parse(await window.ipc.DashboardIPC.get_settings());
            if (descriptor.error) {
                console.error('Failed to update agent denylist:', descriptor.error);
                return;
            }
            const denylist = descriptor.agent_denylist ?? [];
            if (denylist.includes(agentName)) return;
            const result = await saveDenylist(window.ipc.DashboardIPC, [...denylist, agentName]);
            if (!result.ok) console.error('Failed to add agent to denylist:', result.error);
        } catch (err) {
            console.error('Failed to update agent denylist:', err);
        }
    });

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
    sortSelect?.addEventListener('change', (e) => {
        sortGrid(e.target.value, grid);
        changePreference('sort', e.target.value);
    });
    document.querySelector('.close-btn')?.addEventListener('click', closeModal);
    document.getElementById('modal-search')?.addEventListener('input', refreshModal);
    historyFilter?.addEventListener('change', (e) => {
        refreshModal();
        changePreference('history_filter', e.target.value);
    });

    // Close modal on background click
    window.onclick = (event) => {
        if (event.target === modal) closeModal();
        if (event.target === cardMenuModal) closeMenu();
    };

    // Initialize IPC with Python backend
    let staleThresholdMs = 120000;
    let maxActiveAgents = 100;
    try {
        if (!window.pyloid) return;

        // Restoring preferences must not delay IPC setup, so it isn't awaited.
        preferences = createPreferenceSaver(window.ipc?.DashboardIPC);
        window.addEventListener?.('pagehide', preferences.flush);
        restorePreferences(window.ipc?.DashboardIPC, {
            cached: initialTheme,
            changed: changedPreferences,
            applyTheme,
            applySort: (sort) => {
                if (grid.children.length) sortGrid(sort, grid);
            },
            save: preferences.save,
            sortSelect,
            historyFilter,
        });

        initSettings(window.ipc?.DashboardIPC);

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
                    if (ensureAgentCapacity(maxActiveAgents).includes(currentHistoryKey)) closeModal();
                    card = createCard(data, window.ipc, (opener) => {
                        currentHistoryKey = key; // Lock modal to this agent
                        historyOpener = opener;
                        openHistoryModal(key, agents);
                    }, (opener) => {
                        currentMenuKey = key;
                        menuOpener = opener;
                        openDialog(cardMenuModal);
                    });
                    agents[key] = card;
                    grid.appendChild(card);
                } else if (isHidden(card)) {
                    // A hidden card reappears on its next event.
                    setHidden(card, false);
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
            onSettingsChanged: (changed) => {
                staleThresholdMs = changed.stale_threshold * 1000;
                maxActiveAgents = changed.max_active_agents;
                if (evictAgents(maxActiveAgents).includes(currentHistoryKey)) closeModal();

                const denylist = new Set(changed.agent_denylist ?? []);
                for (const [key, card] of Object.entries(agents)) {
                    if (!denylist.has(card.querySelector('.agent-name')?.textContent)) continue;
                    card.remove();
                    removeAgent(key);
                    if (key === currentHistoryKey) closeModal();
                    if (key === currentMenuKey) closeMenu();
                }

                checkStaleness(agents, staleThresholdMs);
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
