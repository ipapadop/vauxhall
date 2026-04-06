const grid = document.getElementById('agent-grid');
const agents = {}; // (agent, workspace) -> DOM element

// Use global pyloid object if not using modules
const pyloidEvent = window.pyloid.event;
const pyloidIpc = window.pyloid.ipc;

pyloidEvent.listen('agent-update', (data) => {
    const key = `${data.agent}:${data.workspace}`;
    let card = agents[key];

    if (!card) {
        card = createCard(data);
        agents[key] = card;
        grid.appendChild(card);
    }

    updateCard(card, data);
});

function createCard(data) {
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
