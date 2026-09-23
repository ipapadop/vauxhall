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
Vauxhall doesn't support MQTT authentication or TLS yet (issue #3), so the
broker is the only access control:

- The default, `localhost:1883` without authentication, is for **local
  development only**: the broker, dashboard, and agents on one machine, used
  by one person. Mosquitto 2 listens only on the loopback interface when
  started without a configuration file.
- Never expose the broker on a network interface. To monitor agents on other
  machines, forward the port over SSH as described in
  [remote-deployment.md](remote-deployment.md).
- On a shared machine, other local accounts can connect to a loopback broker
  too.

The dashboard's own UI server listens only on `127.0.0.1`.

## What every event contains

| Field | Contents |
| --- | --- |
| `agent` | `Claude Code`, `Codex`, or `Gemini CLI` |
| `workspace` | The absolute path of the directory the agent runs in, which often includes your user name and project names |
| `session_id` | The agent's own session ID, or a SHA-256 hash of its transcript path |
| `state` | One of the [supported states](integrations.md#supported-states) |

The MQTT topic, `vauxhall/agents/<agent>/activity`, carries the agent name.

## What each integration publishes

Values that can hold text you or the agent wrote are in **bold**. Text fields
are limited to 4,096 characters; longer assistant messages are cut off with an
ellipsis.

| `details` field | Claude Code | Codex | Gemini CLI |
| --- | --- | --- | --- |
| `prompt` | **Your submitted prompt**; **questions** from `AskUserQuestion`; **the `description`** of a tool awaiting permission; **notification messages** | **Your submitted prompt**; **questions** from `request_user_input`; **the `description`** of a tool awaiting permission | **Your submitted prompt**; **questions** from `ask_user`; **permission notification messages** |
| `message` | **Assistant messages**, when each is complete | **The final assistant message**, and **interim commentary** read from Codex's local session record | **Model response text**, when each response is complete |
| `tool` | Tool name | Tool name | Tool name |
| `cmd` | **Command text** of `Bash` and `PowerShell` calls; the subagent type | **Command text** of `Bash` calls; the subagent type | **Command text** of `run_shell_command`; the **file path** for `read_file`, `write_file`, and `replace` |
| `args` | Not sent | Not sent | **The complete tool input as JSON**, see below |
| `status` | Fixed values such as `completed`, `failed`, `Ready`, `Session started` | Same | Same |
| `error` | Fixed text: `Tool reported an error` or `API error: <error type>` | Fixed text, or `Bash failed (exit code <n>)` | Fixed text: `Tool reported an error` |
| `duration` | Tool duration in seconds | Tool duration in seconds | Tool duration in seconds |
| `tokens` | Not sent | Not sent | Token count reported by the model |

> [!WARNING]
> **Gemini CLI publishes the complete input of every tool call** in `args`.
> For `write_file` that includes the file contents, and for `replace` the old
> and new text, whenever the JSON fits in 4,096 characters (larger events fail
> validation and aren't sent at all). Issue #3 tracks replacing this with an
> allowlist. Until then, don't use the Gemini CLI hooks in workspaces that
> hold secrets, or remove the `vauxhall-acting` (`BeforeTool`) handler from
> `.gemini/settings.json`.

Never published by any integration: tool output (`tool_response`), error
details and messages from the agent, file contents (except through Gemini
`args`), transcripts, and environment variables.

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

- **Dashboard**: Telemetry is held in memory only, for at most
  `max_active_agents` cards with 20 events each, and is gone when a card is
  evicted or cleared or the dashboard exits. The dashboard doesn't write
  telemetry to disk. Its logs contain agent names, topics, and connection
  details, never payload values.
- **Broker**: Hooks publish at QoS 1 without the retain flag, and the dashboard
  connects with a clean session, so the broker doesn't keep telemetry for
  later subscribers. Check your broker's own logging and persistence
  settings; Mosquitto doesn't log payloads by default.
- **Clipboard**: Clicking a card copies its workspace path.

### On disk

The hooks keep short-lived files in owner-only directories in the system
temporary directory, named `vauxhall-<agent>-<uid>`,
`vauxhall-messages-<agent>-<uid>`, and `vauxhall-codex-cursors-<uid>`
(without the `-<uid>` suffix on Windows):

- Tool start times, under hashed names, deleted when the tool finishes.
- **The text of an assistant message** while it is still being displayed,
  deleted when it is published, or after 24 hours if the message never
  finishes.
- For Codex, the byte offset already read from each session record.

## Reporting a privacy problem

Report anything that sends more than this page describes as a security issue
through the repository's
[security advisories](https://github.com/ipapadop/vauxhall/security/advisories).
