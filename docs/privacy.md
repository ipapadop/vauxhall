<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Privacy and Data Handling

Vauxhall's hooks copy parts of what your agents do into MQTT messages.
Prompts, shell commands, and assistant messages can contain secrets, such as a
token pasted into a prompt or an `export API_KEY=...` command. Read this page
before sending telemetry anywhere other than your own machine.

## Who can see telemetry

Anyone who can connect to the MQTT broker can subscribe to
`vauxhall/agents/#` and read every message, and can publish fake telemetry.
The broker is the access control:

- The default, `localhost:1883` without authentication, is for **local
  development only**: the broker, dashboard, and agents on one machine, used
  by one person. Mosquitto 2 listens only on the loopback interface when
  started without a configuration file.
- Never expose an unauthenticated broker on a network interface. To monitor
  agents on other machines, forward the port over SSH or run a broker that
  requires TLS and passwords, as described in
  [remote-deployment.md](remote-deployment.md).
- A password stops strangers, but every identity that has one can still read
  and publish everything its ACL allows. Restrict reading telemetry to the
  dashboard's identity, as the example there does.
- On a shared machine, other local accounts can connect to a loopback broker
  too.

The dashboard's own UI server listens only on `127.0.0.1`.

## What every event contains

| Field | Contents |
| --- | --- |
| `agent` | `Claude Code`, `Codex`, or `Gemini CLI` |
| `workspace` | The absolute path of the directory the agent runs in, which often includes your user name and project names |
| `session_id` | The agent's own session ID, or a SHA-256 hash of its transcript path; an ID over 256 characters is replaced by its SHA-256 hash |
| `state` | One of the [supported states](integrations.md#supported-states) |

The MQTT topic, `vauxhall/agents/<agent>/activity`, carries the agent name.

## What each integration publishes

Values that can hold text you or the agent wrote are in **bold**. Text fields
are limited to 4,096 characters; longer values are cut off with an ellipsis,
except Gemini CLI's `args`, which is left out. A `workspace` over 4,096
characters keeps its first 24 and last 48 characters and gains part of a
SHA-256 hash of the full path.

| `details` field | Claude Code | Codex | Gemini CLI |
| --- | --- | --- | --- |
| `prompt` | **Your submitted prompt**; **questions** from `AskUserQuestion`; **the `description`** of a tool awaiting permission; **notification messages**; **MCP elicitation messages** | **Your submitted prompt**; **questions** from `request_user_input`; **the `description`** of a tool awaiting permission | **Your submitted prompt**; **questions** from `ask_user`; **permission notification messages** |
| `message` | **Assistant messages**, when each is complete | **The final assistant message**, and **interim commentary** read from Codex's local session record | **Model response text**, when each response is complete |
| `tool` | Tool name | Tool name | Tool name |
| `cmd` | **Command text** of `Bash` and `PowerShell` calls; the subagent type | **Command text** of `Bash` calls; the subagent type | **Command text** of `run_shell_command`; the **file path** for `read_file`, `write_file`, and `replace` |
| `args` | Not sent | Not sent | **The complete tool input as JSON**, see below |
| `status` | Fixed values such as `completed`, `failed`, `Ready`, `Session started`; the tool name in `Denied by auto mode: <tool>` | Same | Same |
| `error` | Fixed text: `Tool reported an error` or `API error: <error type>` | Fixed text, or `Bash failed (exit code <n>)` | Fixed text: `Tool reported an error` |
| `duration` | Tool duration in seconds | Tool duration in seconds | Tool duration in seconds |
| `tokens` | Not sent | Not sent | Token count reported by the model |
| `end_reason` | Documented `SessionEnd` reason: `clear`, `resume`, `logout`, or `prompt_input_exit` | Not sent | Documented `SessionEnd` reason: `exit`, `clear`, `logout`, or `prompt_input_exit` |

> [!WARNING]
> **Gemini CLI publishes the complete input of every tool call** in `args`.
> For `write_file` that includes the file contents, and for `replace` the old
> and new text, whenever the JSON fits in 4,096 characters (a larger input is
> left out of the event rather than cut off). Issue #3 tracks replacing this
> with an allowlist. Until then, don't use the Gemini CLI hooks in workspaces
> that hold secrets, or remove the `vauxhall-acting` (`BeforeTool`) handler
> from `.gemini/settings.json`.

Never published by any integration: tool output (`tool_response`), error
details and messages from the agent, transcripts, and environment variables.
File contents are published only through Gemini `args` and through command
text that holds them, such as a heredoc that writes a file (its first 4,096
characters when longer).

## Controlling what is sent

There are no per-field switches yet; issue #3 plans separate settings for
prompt and command capture. Today you can:

- **Install hooks only where you want them.** Hooks are registered per
  workspace, so a workspace without `vauxhall-hook-install` sends nothing.
- **Remove individual handlers.** Every handler is independent. For example,
  removing the `UserPromptSubmit` handler (Claude Code, Codex) or the
  `vauxhall-thinking` handler (Gemini CLI) stops prompts from being sent.
  See [integrations.md](integrations.md) for which event sends what.
- **Uninstall the hooks** as described in the
  [README](../README.md#uninstalling).
- **Keep the broker private**, as described above.
- **Denylist an agent in the dashboard.** A card's ⋮ menu can add that agent's
  name to `dashboard.agent_denylist` (see
  [configuration.md](configuration.md#denylisted-agents)). This only changes
  what the dashboard keeps and shows: the hook still publishes telemetry for
  that agent to the broker, and any other subscriber still receives it. To
  stop sending it at all, use one of the options above instead.

## Retention

- **Dashboard**: Telemetry content is held in memory only, for at most
  `max_active_agents` cards with 20 events each, and is gone when a card is
  evicted or cleared or the dashboard exits. The dashboard doesn't write
  prompts, messages, commands, tool arguments, errors, tokens, duration, or
  activity history to disk. Its logs contain agent names, topics, and
  connection details, never payload values.
- **Card identities**: To redraw the grid on the next start, the dashboard
  saves each card's `agent`, `workspace`, `session_id`, last known `state`,
  `env`, and last-seen time to `~/.config/vauxhall/dashboard_cards.json`.
  This is a subset of what every event already contains (see above); no
  event content is included. **Clear** and **Clear Stale** remove the
  matching cards from this file too. See
  [configuration.md](configuration.md#remembered-view).
- **Install directory**: The last directory chosen with **Install Hooks…** is
  saved in `~/.config/vauxhall/dashboard_state.json`, so the picker opens
  there next time. It is never published.
- **Broker**: Hooks publish at QoS 1 without the retain flag, and the dashboard
  connects with a clean session, so the broker doesn't keep telemetry for
  later subscribers. Check your broker's own logging and persistence
  settings; Mosquitto doesn't log payloads by default.
- **Clipboard**: The activity pane's **Copy path** button copies the card's
  workspace path.
- **Desktop notifications**: The **Notify me** checkbox is off by default. When
  checked, a card that starts needing attention triggers an OS notification
  (through `Pyloid.show_notification`) containing the agent name and the
  card's latest prompt, message, or error text. The OS, not Vauxhall, decides
  how long that notification (and any lock-screen preview or notification
  history it keeps) is retained.

### On disk

The hooks keep short-lived files in owner-only directories in the system
temporary directory, named `vauxhall-<agent>-<uid>`,
`vauxhall-messages-<agent>-<uid>`, and `vauxhall-codex-cursors-<uid>`
(without the `-<uid>` suffix on Windows). A directory with that name that
another account owns is not used; one you own that others can reach is made
owner-only, and entries other accounts put in it are removed:

- Tool start times, under hashed names, deleted when the tool finishes, or
  after 24 hours if it never does.
- **The text of an assistant message** while it is still being displayed,
  deleted when it is published, or after 24 hours if the message never
  finishes.
- For Codex, the byte offset already read from each session record.

Earlier development builds also wrote a record of each tmux session's pane
to `~/.config/vauxhall/panes/`. Current versions neither write nor read it,
so you can delete that directory.

## Reporting a privacy problem

Report anything that sends more than this page describes as a security issue
through the repository's
[security advisories](https://github.com/ipapadop/vauxhall/security/advisories).
