/**
 * SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
 * SPDX-License-Identifier: MIT
 */

interface AgentData {
    agent: string;
    workspace: string;
    state: string;
    env?: string;
    details?: {
        tool?: string;
        cmd?: string;
        prompt?: string;
        error?: string;
        status?: string;
        tokens?: number;
        duration?: number;
    };
}

interface AgentHistoryItem {
    time: string;
    state: string;
    details: any;
}

interface AgentHTMLElement extends HTMLElement {
    history?: AgentHistoryItem[];
    tokenHistory?: number[];
    latestTokens?: number | null;
    latestDuration?: number | null;
    lastLogMessage?: string;
}

interface PyloidEvent {
    listen(name: string, callback: (data: any) => void): void;
}

interface DashboardIPC {
    open_url(url: string): Promise<void>;
    get_stale_threshold(): Promise<number>;
    ping(): Promise<boolean>;
    set_ready(): Promise<void>;
    copy_to_clipboard(text: string): Promise<boolean>;
}

interface Window {
    pyloid: {
        event?: PyloidEvent;
        EventAPI?: PyloidEvent;
    };
    ipc: {
        DashboardIPC: DashboardIPC;
    };
}
