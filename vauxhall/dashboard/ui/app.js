/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file app.js
 * @description Main entry point for the Vauxhall Dashboard frontend.
 */

import { agentKey, agents, updateAgentHistory, updateLastSeen, clearAgents, removeAgent, ensureAgentCapacity, evictAgents, isHidden, setHidden, snapshotAgents } from './js/state.js';
import { createCard, updateCard, filterGrid, sortGrid, checkStaleness, openHistoryModal, closeHistoryModal, renderSummary } from './js/ui.js';
import { closeDialog, openDialog } from './js/dialog.js';
import { saveDenylist } from './js/denylist.js';
import { handleAck, sendPrompt } from './js/prompt.js';
import { initIPC } from './js/ipc.js';
import { initSettings } from './js/settings.js';
import { cacheTheme, cachedTheme, createDebounce, createPreferenceSaver, isTheme, restorePreferences } from './js/preferences.js';

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
    const attentionFirstToggle = document.getElementById('attention-first-toggle');
    const notifyToggle = document.getElementById('notify-toggle');
    const modal = document.getElementById('history-modal');
    const historyFilter = document.getElementById('modal-state-filter');
    const summaryContainer = document.getElementById('fleet-summary');
    const refreshSummary = () => renderSummary(summaryContainer, agents);
    refreshSummary();

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
            if (descriptor.agent_denylist_editable === false) {
                console.error('Failed to add agent to denylist: a configuration file in the current directory takes precedence.');
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

    // Tracks which agent card the prompt dialog is sending to.
    const promptModal = document.getElementById('prompt-modal');
    const promptForm = document.getElementById('prompt-form');
    const promptText = document.getElementById('prompt-text');
    const promptError = document.getElementById('prompt-error');
    const promptSend = document.getElementById('prompt-send');
    let currentPromptKey = null;
    let promptOpener = null;
    const closePrompt = () => { if (promptModal) closeDialog(promptModal); };
    promptModal?.addEventListener('close', () => {
        currentPromptKey = null;
        (promptOpener?.isConnected ? promptOpener : grid).focus?.();
        promptOpener = null;
    });
    document.getElementById('prompt-close')?.addEventListener('click', closePrompt);
    document.getElementById('prompt-cancel')?.addEventListener('click', closePrompt);
    promptForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const card = agents[currentPromptKey];
        if (!card || !window.ipc?.DashboardIPC) return;
        promptError.textContent = '';
        promptSend.disabled = true;
        try {
            const result = await sendPrompt(window.ipc.DashboardIPC, card, promptText.value);
            if (result.ok) {
                promptText.value = '';
                closePrompt();
            } else {
                promptError.textContent = result.error;
            }
        } finally {
            promptSend.disabled = false;
        }
    });
    const openPrompt = (key, opener) => {
        const card = agents[key];
        if (!card) return;
        currentPromptKey = key;
        promptOpener = opener;
        promptError.textContent = '';
        // Text typed while the agent shows a question or permission dialog
        // answers that dialog, so say so before the user sends anything.
        document.getElementById('prompt-warning').textContent = card.classList.contains('waiting')
            ? 'This agent is waiting for input. What you send will answer its current question or permission request.'
            : '';
        document.getElementById('prompt-target').textContent =
            `${card.querySelector('.agent-name')?.textContent} in ${card.querySelector('.agent-workspace')?.textContent}`;
        openDialog(promptModal);
        promptText.focus?.();
    };

    // Builds a card whose history, options, and prompt buttons act on its key.
    const newCard = (key, data) => createCard(data, window.ipc, (opener) => {
        currentHistoryKey = key; // Lock modal to this agent
        historyOpener = opener;
        openHistoryModal(key, agents);
    }, (opener) => {
        currentMenuKey = key;
        menuOpener = opener;
        openDialog(cardMenuModal);
    }, (opener) => openPrompt(key, opener));

    // Persists card identity and last known state (never prompt, message,
    // command, error, token, or history content) so the grid can be redrawn
    // on the next start. Debounced like preferences, flushed on pagehide.
    const cardSave = createDebounce(() => {
        if (!window.ipc?.DashboardIPC?.save_cards) return;
        Promise.resolve(window.ipc.DashboardIPC.save_cards(JSON.stringify(snapshotAgents(agents))))
            .then(saved => { if (saved === false) console.error('Failed to save card state'); })
            .catch(err => console.error('Failed to save card state:', err));
    }, 500);
    const scheduleCardSave = () => {
        if (window.ipc?.DashboardIPC?.save_cards) cardSave.schedule();
    };
    window.addEventListener?.('pagehide', cardSave.flush);

    // Set when Clear runs while the startup restore (below) is still awaiting
    // get_saved_cards(), so that in-flight response doesn't repopulate the
    // grid the user just emptied.
    let restoreCancelled = false;

    document.getElementById('clear-btn')?.addEventListener('click', () => {
        grid.innerHTML = '';
        clearAgents();
        closePrompt();
        restoreCancelled = true;
        refreshSummary();
        scheduleCardSave();
    });

    document.getElementById('clear-stale-btn')?.addEventListener('click', () => {
        for (const [key, card] of Object.entries(agents)) {
            if (card.classList.contains('stale')) {
                card.remove();
                removeAgent(key);
                if (key === currentPromptKey) closePrompt();
            }
        }
        refreshSummary();
        scheduleCardSave();
    });

    searchInput?.addEventListener('input', (e) => filterGrid(e.target.value.toLowerCase(), agents));
    sortSelect?.addEventListener('change', (e) => {
        sortGrid(e.target.value, grid, attentionFirstToggle?.checked);
        changePreference('sort', e.target.value);
    });
    attentionFirstToggle?.addEventListener('change', (e) => {
        if (sortSelect?.value) sortGrid(sortSelect.value, grid, e.target.checked);
        changePreference('attention_first', e.target.checked);
    });
    notifyToggle?.addEventListener('change', (e) => {
        changePreference('notify', e.target.checked);
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
        if (event.target === promptModal) closePrompt();
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
            applySort: (sort, attentionFirst) => {
                if (grid.children.length) sortGrid(sort, grid, attentionFirst);
            },
            save: preferences.save,
            sortSelect,
            historyFilter,
            attentionFirstToggle,
            notifyToggle,
        });

        initSettings(window.ipc?.DashboardIPC);

        if (window.ipc?.DashboardIPC) {
            try {
                maxActiveAgents = await window.ipc.DashboardIPC.get_max_active_agents();
                console.log(`Maximum active agents set to ${maxActiveAgents}`);
            } catch (err) {
                console.error("Failed to fetch maximum active agents:", err);
            }
            try {
                staleThresholdMs = (await window.ipc.DashboardIPC.get_stale_threshold()) * 1000;
                console.log(`Stale threshold set to ${staleThresholdMs}ms`);
            } catch (err) {
                console.error("Failed to fetch stale threshold:", err);
            }
        }

        // Restore card shells from the previous run before live telemetry
        // starts, so an incoming event for a restored session updates it in
        // place instead of creating a duplicate card. Capped and sorted by
        // last-seen before any DOM work, so a saved list larger than the
        // configured limit doesn't build cards only to evict them.
        if (window.ipc?.DashboardIPC?.get_saved_cards) {
            try {
                const saved = JSON.parse(await window.ipc.DashboardIPC.get_saved_cards());
                // A Clear click while the call above was in flight already
                // emptied the grid; don't let this response undo it.
                if (!restoreCancelled) {
                    const shells = (Array.isArray(saved) ? saved : [])
                        .sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0))
                        .slice(0, Math.max(maxActiveAgents, 0));
                    for (const shell of shells) {
                        const key = agentKey(shell);
                        if (agents[key]) continue;
                        const card = newCard(key, shell);
                        // No history content is persisted; an empty array
                        // (rather than leaving this undefined) lets the
                        // history modal open showing "no events yet" instead
                        // of silently no-op'ing.
                        card.history = [];
                        updateCard(card, shell);
                        card.dataset.lastSeen = String(shell.last_seen || 0);
                        agents[key] = card;
                        grid.appendChild(card);
                    }
                    checkStaleness(agents, staleThresholdMs);
                    if (grid.children.length) sortGrid(sortSelect?.value, grid, attentionFirstToggle?.checked);
                    refreshSummary();
                }
            } catch (err) {
                console.error("Failed to restore saved cards:", err);
            }
        }

        initIPC({
            onAgentUpdate: (data) => {
                const key = agentKey(data);
                let card = agents[key];

                if (!card) {
                    const evicted = ensureAgentCapacity(maxActiveAgents);
                    if (evicted.includes(currentHistoryKey)) closeModal();
                    if (evicted.includes(currentMenuKey)) closeMenu();
                    if (evicted.includes(currentPromptKey)) closePrompt();
                    card = newCard(key, data);
                    agents[key] = card;
                    grid.appendChild(card);
                } else if (isHidden(card)) {
                    // A hidden card reappears on its next event.
                    setHidden(card, false);
                }

                updateAgentHistory(card, data);
                updateLastSeen(card);
                const { enteredAttention, message } = updateCard(card, data);
                if (enteredAttention && notifyToggle?.checked) {
                    window.ipc?.DashboardIPC?.notify(`${data.agent || 'Agent'} needs attention`, message);
                }

                // Push live updates to the history modal if it's viewing this agent
                if (currentHistoryKey === key) openHistoryModal(key, agents, true);

                // Re-apply filter and sort to keep view consistent
                if (searchInput?.value) filterGrid(searchInput.value.toLowerCase(), agents);
                if (sortSelect?.value) sortGrid(sortSelect.value, grid, attentionFirstToggle?.checked);
                refreshSummary();
                scheduleCardSave();
            },
            onStatusUpdate: (msg) => {
                if (status) status.innerText = msg;
            },
            onSettingsChanged: (changed) => {
                staleThresholdMs = changed.stale_threshold * 1000;
                maxActiveAgents = changed.max_active_agents;
                const evicted = evictAgents(maxActiveAgents);
                if (evicted.includes(currentHistoryKey)) closeModal();
                if (evicted.includes(currentMenuKey)) closeMenu();
                if (evicted.includes(currentPromptKey)) closePrompt();

                const denylist = new Set(changed.agent_denylist ?? []);
                for (const [key, card] of Object.entries(agents)) {
                    if (!denylist.has(card.querySelector('.agent-name')?.textContent)) continue;
                    card.remove();
                    removeAgent(key);
                    if (key === currentHistoryKey) closeModal();
                    if (key === currentMenuKey) closeMenu();
                    if (key === currentPromptKey) closePrompt();
                }

                checkStaleness(agents, staleThresholdMs);
                refreshSummary();
                scheduleCardSave();
            },
            onPromptAck: handleAck,
            onReady: () => {
                if (status) status.innerText = "Connected to Agent Fleet";
            },
            onError: (err) => {
                console.error("IPC Error:", err);
                if (status) status.innerText = err;
            }
        });

        // Start staleness check every 10 seconds
        setInterval(() => {
            checkStaleness(agents, staleThresholdMs);
            refreshSummary();
        }, 10000);
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
