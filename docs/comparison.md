<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Comparison with Similar Tools

Many open-source dashboards show what coding agents are doing. Few combine
Vauxhall's three traits: Claude Code, Codex, and Gemini CLI in one view; an
MQTT broker that collects telemetry from many machines; and a monitor-only
design that sends nothing back to the agents.

This page covers open-source tools that show the live status of terminal
coding agents, as described in their READMEs on 2026-10-28. "Not documented"
means the README is silent, not that the feature is absent. Orchestrators
that launch and assign work to agents, such as
[agentgrid](https://github.com/Latencius/agentgrid), overlap only in their
status views and are left out.

## How the tools collect activity

- **Hook, local server, web UI.**
  [claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability)
  (disler): Python hooks POST to a Bun server with SQLite; Vue dashboard;
  text-to-speech alerts.
  [agents-observe](https://github.com/simple10/agents-observe) (simple10): a
  Node hook CLI POSTs to a Hono server; React timeline with token and cost
  stats.
  [Claude-Code-Agent-Monitor](https://github.com/hoangsonww/Claude-Code-Agent-Monitor)
  (hoangsonww): Express and SQLite, a Kanban board, web push, macOS and
  Windows apps; it mirrors other machines' transcripts over SSH and can
  launch and resume agents.
- **Hook, MQTT, home automation.**
  [Claude Fleet](https://github.com/leftover-salmon/home-assistant-claude-fleet):
  a shell hook publishes with `mosquitto_pub`; Home Assistant sensors and a
  YAML dashboard show one row per computer, with phone alerts. This is the
  closest design to Vauxhall's.
- **Hook, local file, desktop or terminal.**
  [claude-code-monitor](https://github.com/onikan27/claude-code-monitor)
  (onikan27): file-based state, a TUI and a mobile web UI; focuses and types
  into iTerm2, Terminal.app, and Ghostty; macOS only.
  [eyes-on-claude-code](https://github.com/joe-re/eyes-on-claude-code)
  (joe-re): hooks append JSONL; a Tauri tray app shows sessions and drives
  tmux panes.
- **Transcript files.**
  [claude-view](https://github.com/tombelieber/claude-view) (tombelieber): a
  Rust and SQLite index over the JSONL in `~/.claude/projects`; React views;
  chat into live sessions.
  [claude-code-dashboard](https://github.com/Stargx/claude-code-dashboard)
  (Stargx): watches the same JSONL; a single-file React page.
  [lazyagent](https://github.com/illegalstudio/lazyagent): a Go TUI and
  desktop app over the transcripts of 9 agents.
- **Processes or OpenTelemetry.**
  [c9watch](https://www.everydev.ai/tools/c9watch) (minchenlee): scans OS
  processes; macOS only. Its details come from a third-party listing, not its
  README.
  [ai-coding-agent-observatory](https://github.com/A-Locke/ai-coding-agent-observatory)
  (A-Locke): each agent's native OpenTelemetry, through a collector, into a
  Next.js dashboard, with an optional AWS path.

## Feature comparison

Only Vauxhall and the OpenTelemetry observatory cover Claude Code, Codex, and
Gemini CLI together. Three tools collect from many machines: Vauxhall and
Claude Fleet receive live hook events over MQTT, and Claude-Code-Agent-Monitor
copies transcripts over SSH or accepts pushes over authenticated HTTP. Rows
are ordered by closeness to Vauxhall's design.

| Tool | Agents | Collection and transport | UI | OS | Many machines | Acts on agents | Alerts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Vauxhall** | Claude Code, Codex, Gemini CLI | Hooks, MQTT QoS 1 with authentication and TLS | Desktop app (Pyloid) | Linux, macOS, Windows | Yes, any host that reaches the broker | No, monitor-only | OS notifications |
| Claude Fleet | Claude Code | Shell hook, MQTT with authentication | Home Assistant dashboard | macOS, Linux, WSL | Yes, one row per computer | No | Phone alerts, status light |
| ai-coding-agent-observatory | Claude Code, Codex, Gemini CLI | Native OpenTelemetry, collector | Web (Next.js) | Docker | Optional AWS mirror | No | Not documented |
| claude-code-hooks-multi-agent-observability | Claude Code | Hooks, HTTP, WebSocket | Web (Vue) | Bun, localhost | Not documented | No | Text-to-speech |
| agents-observe | Claude Code (Codex planned) | Hooks, HTTP, WebSocket | Web (React) | Node or Docker | Not documented | No | Browser bell |
| Claude-Code-Agent-Monitor | Claude Code, Codex, Cursor | Hooks and transcripts, HTTP, WebSocket or SSE | Web, macOS and Windows apps, VS Code | macOS, Windows, containers | Yes: SSH transcript sync every 15 seconds, or token-authenticated HTTP push | Launch, resume, follow-up | Web push, webhooks |
| eyes-on-claude-code | Claude Code | Hooks, JSONL file | Tray and dashboard (Tauri) | macOS (Linux, Windows untested) | No | Types into tmux panes | Sounds |
| claude-code-monitor | Claude Code | Hooks, state files | TUI and mobile web | macOS | No; phone over LAN or Tailscale | Focuses and types into terminals | Not documented |
| claude-view | Claude Code | Transcripts and hooks | Web, mobile app | macOS | No | Chat into live sessions | Not documented |
| lazyagent | 9, including Claude Code and Codex | Transcripts | TUI, desktop, HTTP API | macOS, Linux | Token-protected HTTP API | Reopen sessions | Webhooks |
| claude-code-dashboard | Claude Code | Transcript polling every 2 seconds | Web (single file) | Linux, macOS, Windows | No | No | Not documented |
| c9watch | Claude Code, Codex, Cursor, Pi | OS process scan | macOS app and JSON CLI | macOS | No | Not documented | Not documented |

Every peer that states a license uses MIT, as Vauxhall does.

## Where Vauxhall differs

- **Collection from many machines.** Hooks publish to a broker, so agents on
  laptops, servers, and containers appear on one dashboard as events happen.
  Claude Fleet does the same over MQTT. Claude-Code-Agent-Monitor polls other
  machines' transcripts over SSH every 15 seconds, or accepts authenticated
  HTTP pushes. The other peers document one machine only.
- **Three agents through their hooks.** Hooks report live states such as
  `Waiting for Input`, which drive the attention-first sort and
  notifications. The OpenTelemetry observatory also covers all three agents,
  but its metrics and logs carry no waiting state.
- **Monitor-only.** Nothing flows from the dashboard to the agents.
  Claude-Code-Agent-Monitor, claude-code-monitor, eyes-on-claude-code, and
  claude-view can type into or launch sessions, so their UI is a way into the
  agents.
- **Bounded telemetry that stays off disk.** Both sides validate one shared
  schema; strings over 4,096 characters are cut, and Gemini's `args`, the
  complete tool input, is left out when it is longer. Prompts, commands, and
  smaller Gemini tool inputs are published, as with most peers, but the
  dashboard keeps them in memory only: saved cards hold no prompt, message,
  command, or history. disler's dashboard, agents-observe, and
  Claude-Code-Agent-Monitor store full event payloads in SQLite, and Claude
  Fleet records the last prompt in Home Assistant's database and
  sends the transcript's tail to an LLM for a summary. See
  [privacy.md](privacy.md).
- **Hooks that can't block the agent or be redirected.** A hook waits at
  most 1 second for acknowledgments and always writes valid output.
  `python -P` and a per-user hooks configuration keep a cloned repository
  from replacing the hook code or sending telemetry to its own broker. No
  peer documents either guard.
- **Desktop app on three operating systems.** A packaged startup test runs
  on Linux, macOS, and Windows. Of the peers, only claude-code-dashboard, a
  web page, claims all three; most are macOS first.

The tradeoff: Vauxhall needs a running Mosquitto broker, where file- and
transcript-based tools work after one install command. A single machine gets
the least from it.

## Gaps

| Gap | Peers that have it | Assessment |
| --- | --- | --- |
| Alerts on a phone | Claude Fleet, Claude-Code-Agent-Monitor (web push) | Fits: Home Assistant can subscribe to `vauxhall/agents/+/activity` today; ntfy needs a small MQTT subscriber that forwards to its HTTP publish endpoint. Worth documenting. |
| Subagent and agent-team view | disler, agents-observe, claude-view, Claude-Code-Agent-Monitor | Worth evaluating: group subagent events under the parent card if Claude Code's subagent hooks name the parent session. |
| Cumulative tokens and cost per session, plan limits | agents-observe, claude-view, Claude Fleet | Possible: a running token total per session; cost needs a price table that goes stale. |
| Setup without a broker | claude-code-dashboard, lazyagent, c9watch | Possible: a one-command local broker in the first-run instructions. |
| More agents (Cursor, OpenCode, pi) | lazyagent, c9watch, Claude-Code-Agent-Monitor | Add each when it offers hooks. |
| Searchable history and replay | disler, agents-observe, claude-view | Conflicts: it stores prompts and commands, which Vauxhall does not persist. |
| Focus, type into, or launch sessions | claude-code-monitor, eyes-on-claude-code, Claude-Code-Agent-Monitor | Conflicts: it opens a channel back to the agents. |
| Discovery without hooks (processes, transcripts) | c9watch, claude-view, lazyagent | Conflicts: it sees only the local machine. |
