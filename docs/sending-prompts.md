<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Sending Prompts to Agents

The dashboard can send a prompt to a running agent session. Hooks are
short-lived processes that run once per agent event, so nothing on the agent
side can receive a prompt. A long-lived relay, `vauxhall-relay`, runs on each
agent machine, receives the prompt over MQTT, and types it into the session's
tmux pane. It works for Claude Code, Codex, and Gemini CLI alike, including
while the agent is idle.

> [!WARNING]
> **Anyone who can publish to the broker can type into your agents.** A prompt
> can make an agent run shell commands, so an unauthenticated broker that
> others can reach is remote code execution. Vauxhall has no MQTT
> authentication or ACLs yet (issue #3), and there is no setting that turns
> prompt sending off: it is off only while no relay runs. Use it only with the
> loopback broker or the SSH tunnel described in
> [remote-deployment.md](remote-deployment.md), on machines where you trust
> every account.

## Requirements

- The agent runs in [tmux](https://github.com/tmux/tmux), started **after** the
  hooks were installed. The hooks record the pane at `SessionStart`, so a
  session that was already running has none until it restarts, resumes, or is
  cleared.
- `vauxhall-relay` runs on the machine where the agent runs, as the same user.
  It is installed with the hooks: run it from the hooks environment,
  `.vauxhall-venv/bin/vauxhall-relay`, in any terminal (it doesn't need to be
  in tmux). One relay serves every workspace on the machine.
- The relay reaches the same broker as the hooks; it reads the same
  [hooks configuration](configuration.md) (`vauxhall_hooks.json` or
  `VAUXHALL_MQTT_*`).

## Sending a prompt

1. Click ✉️ on the session's card.
2. Type the prompt and press **Send**.
3. The card shows the outcome under its last-seen time:

| Card text | Meaning |
| --- | --- |
| `Prompt sent, waiting for the relay…` | Published to the broker; no relay has answered yet |
| `Prompt delivered` | The relay pasted the prompt into the pane and pressed Enter |
| `Prompt not delivered: its tmux pane is no longer available` | The pane closed, or tmux restarted since the session started |
| `Prompt not delivered: tmux could not type it in` | A tmux command failed |
| `No relay acknowledged the prompt` | Nothing answered within 10 seconds |

**Delivered** means the text was typed into the pane, not that the agent has
processed it. If the agent is showing a question or permission dialog, the text
answers that dialog, so the prompt dialog warns you when a card is waiting for
input.

A prompt can be up to 4,096 characters, with newlines and tabs but no other
control characters. The dashboard must be connected to the broker; a prompt is
never queued for later.

## How it works

1. At `SessionStart`, each hook records the session's tmux pane in
   `~/.config/vauxhall/panes/`: the pane ID (`$TMUX_PANE`), the tmux server
   socket, and the server's process ID (both from `$TMUX`). It is deleted at
   `SessionEnd`, and a session that starts outside tmux has any earlier record
   removed. Nothing about the pane is published over MQTT.
2. The dashboard publishes `{"schema_version": 1, "id": "...", "text": "..."}`
   at QoS 1, not retained, to
   `vauxhall/agents/<agent>/sessions/<session_id>/prompt`. The agent name is
   lower-case and the session ID is percent-encoded.
3. Every relay subscribed to `vauxhall/agents/+/sessions/+/prompt` looks the
   session up in its own records. A relay that doesn't know the session stays
   silent, so one broker can serve relays on several machines.
4. The relay checks that the recorded tmux server is still the one running,
   then loads the text into a private tmux buffer, pastes it into the pane as
   a bracketed paste, and presses Enter. It never puts the text on a command
   line, so shell and tmux syntax in a prompt isn't interpreted.
5. It publishes `{"schema_version": 1, "id": "...", "status": "delivered"}`
   (or `"failed"` with a `reason`) to `.../ack`, and the dashboard shows it on
   the card. A prompt with an ID the relay already handled is ignored, so a
   redelivery doesn't submit it twice.

Prompts are never retained by the broker, because a retained prompt would be
typed again each time a relay reconnects.

## Troubleshooting

**`No relay acknowledged the prompt`.**

1. Check that `vauxhall-relay` is running on the agent machine and logs
   `Relay connected`.
2. Check that the agent runs in tmux and was started, resumed, or cleared after
   the hooks were installed. `ls ~/.config/vauxhall/panes/` should list a
   record.
3. Check that the relay and the dashboard use the same broker: the relay reads
   the hooks configuration, the dashboard its own.
4. Watch the traffic:
   `mosquitto_sub -t 'vauxhall/agents/+/sessions/#' -v`.

**`its tmux pane is no longer available`.** The pane was closed or tmux was
restarted. Restart the agent in a live pane.

**The text arrives but isn't submitted, or a multi-line prompt is split.**
The relay waits 0.2 seconds between pasting and pressing Enter. An agent
that doesn't treat pasted text as one input can behave differently; please
report the agent and its version.

**The dashboard says `Not connected to the broker`.** See
[troubleshooting.md](troubleshooting.md#broker-connection).
