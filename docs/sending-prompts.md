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
> others can reach is remote code execution. There is no setting that turns
> prompt sending off: it is off only while no relay runs. Use it only with the
> loopback broker, the SSH tunnel, or a broker with TLS, passwords, and an ACL
> that lets only the dashboard publish prompts, all described in
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
| `Prompt not delivered: its tmux pane is no longer available` | The pane closed, tmux restarted, or the agent exited since the session started |
| `Prompt not delivered: tmux could not type it in` | A tmux command failed |
| `Prompt not sent: <reason>` | The dashboard couldn't publish it, for example when not connected to the broker; shown on the card only if you closed the dialog before the answer came, since otherwise the dialog stays open with the reason |
| `No relay acknowledged the prompt` | Nothing answered within 10 seconds; a later answer replaces this text, unless you sent another prompt from the card since |

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
   socket, the server's process ID (both from `$TMUX`), and the process group
   in the pane's foreground, which is the agent's. It is
   deleted at `SessionEnd`, and a session that starts outside tmux has any
   earlier record removed. Nothing about the pane is published over MQTT.
2. The dashboard publishes `{"schema_version": 1, "id": "...", "text": "..."}`
   at QoS 1, not retained, to
   `vauxhall/agents/<agent>/sessions/<session_id>/prompt`. The agent name is
   lower-case and the session ID is percent-encoded.
3. Every relay subscribed to `vauxhall/agents/+/sessions/+/prompt` looks the
   session up in its own records. A relay that doesn't know the session stays
   silent, so one broker can serve relays on several machines.
4. The relay checks that the recorded tmux server is still the one running
   and that the recorded process group is still in the pane's foreground. An
   agent that crashed without ending its session leaves a shell in the pane,
   which would run the prompt as a command, and an agent you start in the
   pane afterwards is another session; both have another process group, so
   the relay refuses. If the session's process group is unknown (it started
   before this check existed, or `ps` didn't answer), the relay can't tell,
   so it refuses too and logs a warning. A wrapper script that runs the agent
   without `exec` and keeps running after it shares its process group, so
   whatever the script starts next in the pane passes the check. It then
   leaves copy mode (or any other tmux mode) if you have the pane in one
   (tmux 3.1a or later),
   loads the text into a private tmux buffer, pastes it into the pane as a
   bracketed paste, and presses Enter. It never puts the text on a command
   line, so shell and tmux syntax in a prompt isn't interpreted.
5. It publishes `{"schema_version": 1, "id": "...", "status": "delivered"}`
   (or `"failed"` with a `reason`) to `.../ack`, and the dashboard shows it on
   the card. A prompt with an ID the relay already handled is ignored, so a
   redelivery doesn't submit it twice.

The dashboard never publishes a retained prompt, because the broker would
replay it each time a relay reconnects. If another client publishes one, a relay
connected at that moment types it once, like any prompt; the broker's later
replays are ignored, so a relay that connects afterwards never types it.

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

**`its tmux pane is no longer available`.** The pane was closed, tmux was
restarted, or the agent that started the session no longer runs in the pane,
even if the same agent was started there again. Send to the card of the
session that runs there now, or restart the agent in a live pane. If the
relay logs `foreground process group at session start is unknown`, the
session started before upgrading, or `ps` lacks `-o tpgid` (as BusyBox's
may): restart the session, and install procps if needed.

**The text arrives but isn't submitted, or a multi-line prompt is split.**
If the pane was in copy mode and tmux is older than 3.1a, the relay can't
leave the mode: leave it yourself (`q`) and send again, or upgrade tmux
(`tmux -V`). The relay waits 0.2 seconds between pasting and pressing Enter. An agent
that doesn't treat pasted text as one input can behave differently; please
report the agent and its version.

**The dashboard says `Not connected to the broker`.** See
[troubleshooting.md](troubleshooting.md#broker-connection).
