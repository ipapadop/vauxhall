const agents = {}; // (agent, workspace) -> DOM element

function init() {
    console.log("Vauxhall Dashboard Initialized");
    const status = document.getElementById('js-status');
    const grid = document.getElementById('agent-grid');
    const clearBtn = document.getElementById('clear-btn');

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            console.log("Clearing dashboard...");
            grid.innerHTML = '';
            // Clear the agents tracking object
            for (const key in agents) {
                delete agents[key];
            }
        });
    }

    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            filterGrid(e.target.value.toLowerCase());
        });
    }

    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            sortGrid(e.target.value);
        });
    }
    
    try {
        if (!window.pyloid) return;

        const pyloidEvent = window.pyloid.event || window.pyloid.EventAPI;
        const pyloidIpc = window.ipc;

        const listener = (data) => {
            const grid = document.getElementById('agent-grid');
            if (!grid) return;

            const key = `${data.agent}:${data.workspace}`;
            let card = agents[key];

            if (!card) {
                card = createCard(data, pyloidIpc);
                agents[key] = card;
                grid.appendChild(card);
            }

            // Track last seen time
            card.dataset.lastSeen = Date.now();
            card.classList.remove('stale');

            updateCard(card, data);

            // Re-apply filter
            const searchInput = document.getElementById('search-input');
            if (searchInput && searchInput.value) {
                filterGrid(searchInput.value.toLowerCase());
            }

            // Re-apply sort if needed (e.g., if set to recent)
            const sortSelect = document.getElementById('sort-select');
            if (sortSelect && sortSelect.value === 'recent') {
                sortGrid('recent');
            }
        };

        if (pyloidEvent && pyloidEvent.listen) {
            pyloidEvent.listen('agent-update', listener);
        }

        // Signal Python that we are ready
        if (pyloidIpc && pyloidIpc.DashboardIPC) {
            pyloidIpc.DashboardIPC.set_ready().then(() => {
                if (status) status.innerText = "Connected to Agent Fleet";
            });
        }

        // Start staleness check every 10 seconds
        setInterval(checkStaleness, 10000);

    } catch (err) {
        console.error("Initialization error:", err);
    }
}

if (window.pyloid) {
    init();
} else {
    window.addEventListener('pyloidReady', init);
    // Fallback: Check every 100ms for 2 seconds
    let checks = 0;
    const interval = setInterval(() => {
        checks++;
        if (window.pyloid) {
            console.log("Pyloid found via interval check");
            init();
            clearInterval(interval);
        } else if (checks > 20) {
            clearInterval(interval);
            console.error("Pyloid not found after 2 seconds");
        }
    }, 100);
}

function filterGrid(query) {
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

function sortGrid(criteria) {
    const grid = document.getElementById('agent-grid');
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
        }
        return 0;
    });

    grid.innerHTML = '';
    sorted.forEach(card => grid.appendChild(card));
}

function createCard(data, pyloidIpc) {
    // Fallback detection
    const env = data.env || (data.workspace.startsWith('/home') || data.workspace.match(/^[A-Z]:\\/) ? 'local' : 'remote');
    
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.innerHTML = `
        <div class="agent-header">
            <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="env-badge env-${env}">${env}</span>
                    <div class="agent-name">${data.agent}</div>
                    <div class="metric-badges"></div>
                </div>
                <div class="agent-workspace">${data.workspace}</div>
            </div>
            <div class="status-badge">Idle</div>
        </div>
        <div class="log-area">Ready...</div>
    `;
    
    card.addEventListener('click', () => {
        pyloidIpc.DashboardIPC.copy_to_clipboard(`cd ${data.workspace}`);
    });
    
    return card;
}

function updateCard(card, data) {
    const statusBadge = card.querySelector('.status-badge');
    const logArea = card.querySelector('.log-area');
    const metricsArea = card.querySelector('.metric-badges');
    
    statusBadge.textContent = data.state;
    
    if (data.state === 'Error') {
        card.classList.add('error');
        card.classList.remove('waiting', 'working');
    } else if (data.state === 'Waiting' || data.state === 'Waiting for Input' || data.state === 'Input Required') {
        card.classList.add('waiting');
        card.classList.remove('error', 'working');
    } else if (data.state === 'Acting' || data.state === 'Thinking') {
        card.classList.add('working');
        card.classList.remove('error', 'waiting');
    } else {
        card.classList.remove('error', 'waiting', 'working');
    }

    // Update Metrics
    const details = data.details || {};
    if (metricsArea) {
        metricsArea.innerHTML = '';
        if (details.tokens) {
            const t = details.tokens > 1000 ? (details.tokens/1000).toFixed(1) + 'k' : details.tokens;
            metricsArea.innerHTML += `<span class="metric-badge tokens">${t}</span>`;
        }
        if (details.duration) {
            metricsArea.innerHTML += `<span class="metric-badge">${details.duration}s</span>`;
        }
    }

    if (details.tool) {
        logArea.textContent = `Running: ${details.tool}\n${details.cmd || ''}`;
    } else if (details.prompt) {
        logArea.textContent = `Prompt: ${details.prompt}`;
    } else {
        logArea.textContent = "Ready...";
    }
}

function checkStaleness() {
    const now = Date.now();
    const threshold = 120000; // 2 minutes

    Object.values(agents).forEach(card => {
        const lastSeen = parseInt(card.dataset.lastSeen);
        if (now - lastSeen > threshold) {
            card.classList.add('stale');
            const statusBadge = card.querySelector('.status-badge');
            if (statusBadge) statusBadge.textContent = 'STALE';
        }
    });
}
