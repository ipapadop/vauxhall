/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

/**
 * @file app.js
 * @description Main entry point for the Vauxhall Dashboard frontend.
 */

import { agentKey, agents, cardIdentity, updateAgentHistory, updateLastSeen, clearAgents, removeAgent, ensureAgentCapacity, evictAgents, isClearedSession, isHidden, isLateFinalMessage, setHidden, snapshotAgents } from './js/state.js';
import { createCard, copyWorkspacePath, updateCard, filterGrid, sortGrid, checkStaleness, openHistoryModal, closeHistoryModal, renderSummary } from './js/ui.js';
import { closeDialog, openDialog } from './js/dialog.js';
import { saveDenylist } from './js/denylist.js';
import { initInstall } from './js/install.js';
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

    // Tracks which card a dialog acts on and the control that opened it. The
    // close button, the backdrop, and Escape all end in the dialog's close
    // event, so the target is reset and focus returned in one place. An opener
    // evicted while the dialog was open, or in a card that is now hidden or
    // filtered out, hands focus to the grid: a hidden control can't take focus.
    const canTakeFocus = (control) =>
        control?.isConnected && control.closest('.agent-card')?.style.display !== 'none';
    const dialogTarget = (dialog) => {
        const target = { key: null, opener: null };
        dialog?.addEventListener('close', () => {
            target.key = null;
            (canTakeFocus(target.opener) ? target.opener : grid).focus?.();
            target.opener = null;
        });
        return target;
    };

    // The card's activity pane (the history modal) follows its live updates.
    const historyTarget = dialogTarget(modal);
    const closeModal = () => closeHistoryModal();
    const refreshModal = () => {
        if (historyTarget.key) openHistoryModal(historyTarget.key, agents, true);
    };

    const cardMenuModal = document.getElementById('card-menu-modal');
    const menuTarget = dialogTarget(cardMenuModal);
    const closeMenu = () => closeDialog(cardMenuModal);
    document.getElementById('card-menu-close')?.addEventListener('click', closeMenu);
    document.getElementById('card-menu-hide')?.addEventListener('click', () => {
        const card = agents[menuTarget.key];
        if (card) setHidden(card, true);
        closeMenu();
    });
    document.getElementById('card-menu-denylist')?.addEventListener('click', async () => {
        const card = agents[menuTarget.key];
        const agentName = card && cardIdentity(card).agent;
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

    // Closes the dialogs acting on any of the given cards, which are leaving
    // the grid.
    const closeDialogsFor = (keys) => {
        if (keys.includes(historyTarget.key)) closeModal();
        if (keys.includes(menuTarget.key)) closeMenu();
    };
    const removeCard = (key) => {
        agents[key]?.remove();
        removeAgent(key);
        closeDialogsFor([key]);
    };

    // Builds a card whose click and options button act on its key.
    const newCard = (key, data) => createCard(data, (opener) => {
        historyTarget.key = key;
        historyTarget.opener = opener;
        openHistoryModal(key, agents);
    }, (opener) => {
        menuTarget.key = key;
        menuTarget.opener = opener;
        openDialog(cardMenuModal);
    });

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
        restoreCancelled = true;
        refreshSummary();
        scheduleCardSave();
    });

    document.getElementById('clear-stale-btn')?.addEventListener('click', () => {
        for (const [key, card] of Object.entries(agents)) {
            if (card.classList.contains('stale')) removeCard(key);
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
    document.getElementById('modal-copy-path')?.addEventListener('click', async () => {
        const key = historyTarget.key;
        const card = agents[key];
        const status = document.getElementById('modal-copy-status');
        if (!card || !status) return;
        // Cleared first, so a repeated outcome is announced again.
        status.textContent = '';
        const { workspace } = cardIdentity(card);
        const outcome = await copyWorkspacePath(window.ipc?.DashboardIPC, workspace);
        // The pane may have closed, moved to another card, or shown the
        // session's next workspace meanwhile.
        if (historyTarget.key === key && cardIdentity(card).workspace === workspace) status.textContent = outcome;
    });
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
            changed: changedPreferences,
            applyTheme,
            applySort: (sort, attentionFirst) => {
                if (grid.children.length) sortGrid(sort, grid, attentionFirst);
            },
            sortSelect,
            historyFilter,
            attentionFirstToggle,
            notifyToggle,
        });

        initSettings(window.ipc?.DashboardIPC);
        const install = initInstall(window.ipc?.DashboardIPC);

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
                if (card && isLateFinalMessage(card, data)) return;

                // A cleared session continues under a new session ID, so its
                // card would only linger until it went stale.
                if (isClearedSession(data)) {
                    if (!card) return;
                    removeCard(key);
                    refreshSummary();
                    scheduleCardSave();
                    return;
                }

                if (!card) {
                    closeDialogsFor(ensureAgentCapacity(maxActiveAgents));
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
                if (historyTarget.key === key) openHistoryModal(key, agents, true);

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

                // Denylisted cards go first, so they don't count toward the limit.
                const denylist = new Set(changed.agent_denylist ?? []);
                for (const [key, card] of Object.entries(agents)) {
                    if (denylist.has(cardIdentity(card).agent)) removeCard(key);
                }
                closeDialogsFor(evictAgents(maxActiveAgents));

                checkStaleness(agents, staleThresholdMs);
                refreshSummary();
                scheduleCardSave();
            },
            onInstallOutput: install?.onOutput,
            onInstallDone: install?.onDone,
            onReady: () => {
                if (status) status.innerText = "Connected to Agent Fleet";
            },
            onError: (err) => {
                console.error("IPC Error:", err);
                if (status) status.innerText = err;
            }
        });

        // Start staleness check every 10 seconds; the open pane's newest
        // entry counts up with it.
        setInterval(() => {
            checkStaleness(agents, staleThresholdMs);
            refreshSummary();
            refreshModal();
        }, 10000);
    } catch (err) {
        console.error("Initialization error:", err);
    }
}

// Entry Point
if (window.pyloid) {
    init();
} else {
    // Whichever of the event and the poll sees Pyloid first starts the
    // dashboard; the other does nothing.
    let started = false;
    const start = () => {
        if (started) return;
        started = true;
        clearInterval(interval);
        init();
    };
    window.addEventListener('pyloidReady', start);

    // Fallback: Check every 100ms for 2 seconds
    let checks = 0;
    const interval = setInterval(() => {
        checks++;
        if (window.pyloid) {
            start();
        } else if (checks > 20) {
            clearInterval(interval);
            console.error("Pyloid not found after 2 seconds");
        }
    }, 100);
}
