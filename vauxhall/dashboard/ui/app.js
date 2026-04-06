const agents = {}; // (agent, workspace) -> DOM element

function init() {
    console.log("Pyloid initialized");
    const pyloidEvent = window.pyloid.event;
    const pyloidIpc = window.pyloid.ipc;

    console.log("Registering agent-update listener...");

    const listener = (data) => {
        console.log("JS received agent-update:", data);
        const grid = document.getElementById('agent-grid');
        if (!grid) {
            console.error("Critical: agent-grid not found during event update!");
            return;
        }

        const key = `${data.agent}:${data.workspace}`;
        let card = agents[key];

        if (!card) {
            console.log("Creating new card for:", key);
            card = createCard(data, pyloidIpc);
            agents[key] = card;
            grid.appendChild(card);
        }

        updateCard(card, data);
    };

    if (pyloidEvent && pyloidEvent.listen) {
        pyloidEvent.listen('agent-update', listener);
        console.log("Using window.pyloid.event.listen");
    } else {
        console.error("Could not find window.pyloid.event.listen");
    }
}

if (window.pyloid) {
    init();
} else {
    window.addEventListener('pyloidReady', init);
}

function createCard(data, pyloidIpc) {
    const card = document.createElement('div');
    card.className = 'agent-card';
    card.innerHTML = `
        <div class="agent-header">
            <div>
                <div class="agent-name">${data.agent}</div>
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
    
    statusBadge.textContent = data.state;
    
    if (data.state === 'Error') {
        card.classList.add('error');
    } else {
        card.classList.remove('error');
    }

    const details = data.details || {};
    if (details.tool) {
        logArea.textContent = `Running: ${details.tool}\n${details.cmd || ''}`;
    }
}
