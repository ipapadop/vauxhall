# Agent Integration Guide

Vauxhall works with any agent that can publish JSON over MQTT. It ships hooks
for Claude Code, Codex, and Gemini CLI; other agents can use `TelemetryClient`
or publish messages directly.

## Publishing Telemetry

### Python Client

```python
from uuid import uuid4

from vauxhall.hooks.client import TelemetryClient

session_id = str(uuid4())
client = TelemetryClient(host="localhost", port=1883)

# Report a running tool with metrics and environment
delivered = client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    session_id=session_id,
    state="Acting",
    env="local",  # Optional: "local" or "remote"
    tool="grep",
    cmd="grep -r 'TODO' .",
    tokens=1245,  # Optional
    duration=12.4,  # Optional, in seconds
)

# Report that the agent is done
client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    session_id=session_id,
    state="Idle",
)
```

`send()` validates the event, publishes it at QoS 1, and waits up to one second
for the broker's acknowledgment. It returns `True` only when the broker
acknowledges the message; validation, connection, and publish failures return
`False` instead of raising. Use the client as a context manager to send several
events over one connection. Importing the client or configuration modules does
not change the host application's logging; the dashboard and hook entry points
configure logging when they run.

### Raw MQTT (Any Language)

Publish JSON to `vauxhall/agents/<agent_name>/activity`:

```json
{
  "schema_version": 1,
  "agent": "AgentName",
  "workspace": "/absolute/path/to/workspace",
  "session_id": "0195db69-a702-73dc-a223-7556293f8cba",
  "state": "Acting",
  "details": {}
}
```

Operation values such as `tool`, `cmd`, `prompt`, `message`, `status`, `error`,
`tokens`, and `duration` go in `details`. The optional `env` field is top-level.

## Telemetry Schema

Version 1 is the only accepted schema.

| Field | Required | Constraint |
| :--- | :--- | :--- |
| `schema_version` | Yes | Integer `1` |
| `agent` | Yes | 1–128 characters |
| `workspace` | Yes | 1–4,096 characters |
| `session_id` | Yes | 1–256 characters |
| `state` | Yes | A [supported state](#supported-states) |
| `env` | No | `local` or `remote` |
| `details` | No | Object with at most 16 entries |

Required fields cannot be blank, and unknown top-level fields are rejected.
`details` keys are strings of at most 64 characters. Values are strings of at
most 4,096 characters, numbers, booleans, or `null`; `tokens` and `duration`
must be numbers, not booleans.

`session_id` is opaque. It must stay the same for a whole session and be unique
among concurrent sessions of the same agent in the same workspace. Generic
producers should generate a UUID when the session starts.

The built-in hooks take the session ID from the agent's native session ID, then
a hash of the transcript path, then the `VAUXHALL_SESSION_ID` environment
variable. If none is available, the hook skips the event.

The dashboard drops messages larger than `max_payload_bytes` (65,536 bytes by
default) before decoding them, and logs and drops malformed or invalid
telemetry. Rejection logs never include payload values. The dashboard and
`TelemetryClient` share one validator, `vauxhall.core.telemetry`.

## Supported States

| State | Card color | Meaning |
| :--- | :--- | :--- |
| `Acting` | 🟢 Green | Running a tool or command |
| `Thinking` | 🟢 Green | Processing or planning |
| `Waiting for Input` | 🟡 Yellow | Waiting for the user |
| `Input Required` | 🟡 Yellow | Same as `Waiting for Input` |
| `Error` | 🔴 Red | A tool or the agent failed |
| `Idle` | None | Finished or on standby |

## Dashboard Behavior

- **Cards**: A card is identified by `agent`, `workspace`, and `session_id`, so
  separate sessions get separate cards. The dashboard keeps up to
  `max_active_agents` cards (100 by default); a new identity at capacity evicts
  the least recently seen card.
- **Environment badge**: Shows `env`. Without it, workspaces starting with
  `/home` or a Windows drive letter (such as `C:\`) are labeled LOCAL, and all
  others REMOTE.
- **Metrics**: Positive `tokens` and `duration` values appear as footer badges.
  They reset when an `Acting` event, or a `Thinking` event with a `prompt`,
  starts a new operation.
- **Activity log**: Each card shows its last 5 events, newest first, with
  `[HH:mm:ss]` timestamps. An event whose message matches the previous one is
  not repeated. The message is, in order of precedence: the prompt for waiting
  states, `Error: <error>`, `Agent: <message>`, `Running: <tool> <cmd>` (or
  `Completed: <tool>` for a completed `Thinking` event), `Prompt: <prompt>`,
  or the status.
- **History**: The 🕒 icon opens a resizable modal with the card's last 20
  events, filterable by text and state. It updates live and follows new events
  only when scrolled to the bottom and not hovered.
- **Staleness**: A card with no events for `stale_threshold` seconds (120 by
  default) turns gray and shows `STALE`. Staleness is checked every 10 seconds.
- **Copying**: Clicking a card copies the raw `workspace` value. Telemetry is
  never inserted into HTML markup or shell commands.
- **Settings**: The ⚙️ button opens a `<dialog>` built from
  `DashboardIPC.get_settings()`, with a source badge, reset button, and inline
  error per field. Read-only fields are disabled with the reason shown. Escape
  or Cancel closes it and focus returns to the button. The hooks option
  appears when an editable MQTT value differs from `hooks_mqtt`, the values
  the hooks use. Save sends only changed values to
  `DashboardIPC.save_settings()`, with `update_hooks` set when the option is
  checked; server errors appear next to the
  named field, and the dialog stays open to show restart or hooks notes. See
  [README.md](README.md#settings-dialog) for when each field takes effect.
- **Remembered view**: The first paint uses the theme cached in the
  `vauxhall-theme` localStorage key. On startup the frontend then applies the
  theme, sort order, and history state filter from
  `DashboardIPC.get_ui_state()` without delaying IPC setup, skipping any
  preference the user already changed, and re-sorts existing cards. If no theme
  is saved, the cached theme (from earlier versions) is saved. Changes are
  batched and sent to `DashboardIPC.save_ui_state()` 500 ms after the last one,
  or immediately on `pagehide`; a `false` result is logged. Theme changes also
  update the localStorage cache.

## Dashboard Internals

- **Pending updates**: Until the frontend signals readiness, the dashboard keeps
  only the newest `pending_update_limit` events (500 by default), dropping the
  oldest. Drop warnings are logged at power-of-two counts and never include
  telemetry.
- **Readiness**: Marking the frontend ready and taking the pending snapshot
  happen under one lock, so no event is lost between the MQTT callback and the
  initial drain. Dispatch is serialized, so live events cannot overtake the
  queued snapshot. Repeated readiness signals have no effect.
- **Connection status**: The status line shows `Connecting...`,
  `Connected to Agent Fleet`, retry messages after connection failures or
  disconnects, and `Disconnected` on shutdown.
- **Saving settings**: `DashboardApp.save_settings` runs under one lock, so
  saves never overlap. It checks the dashboard file and, when requested, the
  hooks file with `check_user_config` before writing either one. It then reloads
  `DashboardConfig`, replaces the running `mqtt`, `logging`, and `dashboard`
  settings, and sets the root log level if it changed. Broker changes stop the
  current `DashboardSubscriber` and start a new one with the new host and port;
  a failed start is logged, and the saved settings stay. If the frontend is
  ready, it receives a `settings-changed` event with the new stale threshold
  and card limit. `vauxhall.hooks.config` is imported lazily, so a malformed
  hooks file only disables the hooks option.
- **View state**: `vauxhall.dashboard.ui_state` reads and writes
  `~/.config/vauxhall/dashboard_state.json`. It keeps only known keys with
  valid values, treats an unreadable file as empty, and writes atomically.
  Each update holds one lock across load, merge, and write, so a frontend save
  and the shutdown window save can't discard each other's fields.
  `save_ui_state` accepts only `theme`, `sort`, and `history_filter`; only
  Python writes `window`. `run()` creates the window with the saved size, calls
  `set_position` only when `visible_position` finds the top edge on a monitor's
  available area, and maximizes after showing the window. When the UI loop
  exits, it saves the size and position from Pyloid's public `get_size`,
  `get_position`, and `is_maximized`. A maximized window keeps its previous
  normal size, and a save failure is logged without blocking shutdown.
- **Shutdown**: When the UI loop exits, including after an exception or partial
  startup failure, the dashboard marks the frontend not ready and stops the
  MQTT client once. The final `Disconnected` status and any late telemetry are
  kept instead of being sent to the destroyed window.
- **Pyloid**: Pyloid 0.27.2 or newer is required. Its `BrowserWindow` marshals
  cross-thread commands to the UI thread, so MQTT callbacks call
  `window.invoke()` directly. Vauxhall does not use Pyloid's private symbols.

## Claude Code

### Event Mapping

| Claude Code event | Vauxhall state |
| :--- | :--- |
| `SessionStart` | `Idle`, with a normalized source; ignored after compaction |
| `UserPromptSubmit` | `Thinking` (with `prompt`) |
| `PreToolUse` | `Acting`; `Waiting for Input` for `AskUserQuestion` |
| `PermissionRequest` | `Waiting for Input` |
| `PostToolUse` | `Thinking` (`completed`); `Idle` (`cancelled`) when interrupted |
| `PostToolUseFailure` | `Error` (`failed`); `Idle` (`cancelled`) for `is_interrupt` |
| `Notification` | `Waiting for Input` for `permission_prompt`, `idle_prompt`, `elicitation_dialog`, and `elicitation_url_dialog`; others are ignored |
| `MessageDisplay` | `Thinking` with the completed assistant message |
| `SubagentStart` | `Acting` (`tool` is `Agent`, `cmd` is the agent type) |
| `PreCompact` | `Thinking` (`Compacting context`, with the trigger) |
| `PostCompact` | `Context compacted`: `Idle` after `manual`, `Thinking` after `auto` |
| `Stop` | `Idle` (`Ready`) |
| `StopFailure` | `Error` (`API error: <error type>`) |
| `SessionEnd` | `Idle`, with a normalized reason |

Events follow the documented
[Claude Code hooks](https://code.claude.com/docs/en/hooks) input fields.
`SessionStart` reports `Session started`, `Session resumed`, `Session cleared`,
or `Session forked`; its `compact` source is ignored because `PostCompact`
reports compaction. `SessionEnd` reports `session cleared`, `session switched`,
`logged out`, or `input closed` for the `clear`, `resume`, `logout`, and
`prompt_input_exit` reasons, and `session ended` otherwise. `StopFailure`
reports the documented error types and `unknown` for anything else.

Some signals are intentionally absent:

- `SubagentStop` is not registered. For a foreground subagent, `PostToolUse`
  for the `Agent` tool already reports completion; for a background subagent,
  it would mark an idle session as working.
- `PreCompact` and `PostCompact` from inside a subagent (with `agent_id`) are
  ignored so they don't change the main session's state.
- Claude Code has no interrupt event, and `Stop` does not fire when the user
  interrupts a turn, so the card keeps its last state until the next event.
- Token counts are not reported. Hook inputs do not include them, and the
  transcript is written asynchronously, so it can lag the current turn.

### Published Data

- Only `Bash` and `PowerShell` tool calls publish their command text. File
  contents and other tool inputs are not published.
- `PermissionRequest` publishes the tool input's `description` as the prompt,
  when present.
- `tool_response` and `error` contents are never published. For `StopFailure`,
  only the error type is published, not `error_details` or the error message.
- `MessageDisplay` batches are assembled in a private temporary file and
  published when the message ends, including messages shown during a turn.
  The file is then removed. Messages longer than 4,096 characters end with
  an ellipsis.
- Tool durations use Claude Code's `duration_ms` when reported. Otherwise they
  use a timing file per session and `tool_use_id` in the system temporary
  directory, so concurrent tool calls do not overwrite each other.

### Failure Handling

As with Codex, the hook writes one JSON object to stdout for every input and
sends logs and configuration errors to stderr.

### Automated Installation

After installing `vauxhall[hooks]`, run from the Claude Code project:

```bash
vauxhall-hook-install claude
```

The installer:

- Backs up `.claude/settings.local.json` to `.claude/settings.local.json.bak`.
  If the file is invalid JSON or has an unexpected structure, it exits with an
  error and leaves the file unchanged.
- Recreates `.vauxhall-venv` and installs `vauxhall[hooks]` into it from the
  same source as the running installer: the same Git commit, local directory,
  or wheel file, or otherwise the matching PyPI release. Agents named in one
  command share that environment, so it is built once.
- Replaces existing Vauxhall handlers, keeps all other settings, registers
  every event above, and replaces the settings file atomically. It uses local
  settings because the command contains a machine-specific path.
- Writes commands that run `python -m vauxhall.hooks.claude.telemetry_hook`,
  quoted the same way as the Codex installer, with a 3-second timeout.

Claude Code reads hooks at startup. Restart it, or open `/hooks` to review the
new hooks.

### Manual Configuration

Add the command handler to each event in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "'/absolute/path/to/.vauxhall-venv/bin/python' -m vauxhall.hooks.claude.telemetry_hook",
            "timeout": 3
          }
        ]
      }
    ],
    "SessionStart": [...],
    "UserPromptSubmit": [...],
    "PermissionRequest": [...],
    "PostToolUse": [...],
    "PostToolUseFailure": [...],
    "Notification": [...],
    "MessageDisplay": [...],
    "SubagentStart": [...],
    "PreCompact": [...],
    "PostCompact": [...],
    "Stop": [...],
    "StopFailure": [...],
    "SessionEnd": [...]
  }
}
```

## Codex

### Event Mapping

| Codex event | Vauxhall state |
| :--- | :--- |
| `SessionStart` | `Idle` (`Session started`, `resumed`, `cleared`, or `forked`); ignored for `compact` |
| `UserPromptSubmit` | `Thinking` |
| `PreToolUse` | `Acting`; `Waiting for Input` for `request_user_input` |
| `PermissionRequest` | `Waiting for Input` |
| `PostToolUse` | `Thinking`, `Error`, or `Idle`, based on the tool result |
| `SubagentStart` | `Acting` (`tool` is `Agent`, `cmd` is the agent type) |
| `PreCompact` | `Thinking` (`Compacting context`, with the trigger) |
| `PostCompact` | `Context compacted`: `Idle` after `manual`, `Thinking` after `auto` |
| `Stop` | `Idle` (`Ready`, with `last_assistant_message` when available) |
| `Interrupt` | `Idle` (`interrupted`) |
| `SessionEnd` | `Idle` (`session ended`) |

`PostToolUse` outcomes follow the documented
[Codex hooks](https://developers.openai.com/codex/hooks/) result fields:

| `tool_response` | State | Status |
| :--- | :--- | :--- |
| Cancellation marker | `Idle` | `cancelled` |
| Non-zero `exit_code` | `Error` | `failed` |
| `isError: true` | `Error` | `failed` |
| `exit_code: 0` or `isError: false` | `Thinking` | `completed` |
| Anything else | `Thinking` | `result unavailable` |

A cancellation marker is `cancelled: true`, `canceled: true`, or a `code`,
`status`, or `name` of `cancelled`, `canceled`, or `aborted`, at the top level
or inside `error`.

Current Codex releases send Bash and `apply_patch` results as output text
without the exit code, so those calls report `result unavailable`. MCP tools
send the MCP `CallToolResult`, whose `isError` field reports failures.
`SessionStart` with the `compact` source is ignored because Codex can run it in
the middle of a turn. Compaction events from subagents (those with `agent_id`)
are ignored so they don't change the main session's state. `SubagentStop` is
not registered, for the same reasons as for Claude Code.

### Published Data

- Only `Bash` tool calls publish their command text. Patch contents and other
  tool inputs are not published.
- `tool_response` content is never published.
- `Stop` publishes the final assistant message. On later tool or stop hooks,
  Vauxhall also reads completed commentary from the current turn in Codex's
  local session record and publishes each once. This is best effort: Codex
  does not provide an interim message hook, the record format can change,
  and its writes may lag. The reader keeps only a private byte cursor in the
  system temporary directory and limits each read to 1 MiB. Messages over
  4,096 characters end with an ellipsis.
- Tool durations use a timing file per session and `tool_use_id` in the system
  temporary directory, so concurrent tool calls do not overwrite each other.

### Failure Handling

The hook loads configuration, logging, and the MQTT client inside its error
boundary. For every input, including unknown events, malformed JSON, invalid
configuration, and telemetry failures, it writes one JSON object to stdout and
exits normally. Logs and configuration errors go to stderr.

### Automated Installation

After installing `vauxhall[hooks]`, run from the Codex workspace:

```bash
vauxhall-hook-install codex
```

The installer:

- Backs up `.codex/hooks.json` to `.codex/hooks.json.bak`. If the file is
  invalid JSON or has an unexpected structure, it exits with an error and leaves
  the file unchanged.
- Recreates `.vauxhall-venv` and installs `vauxhall[hooks]` into it from the
  same source as the running installer: the same Git commit, local directory,
  or wheel file, or otherwise the matching PyPI release. Agents named in one
  command share that environment, so it is built once.
- Replaces existing Vauxhall handlers, keeps all other configuration, and
  registers `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
  `PermissionRequest`, `PostToolUse`, `SubagentStart`, `PreCompact`,
  `PostCompact`, `Stop`, `Interrupt`, and `SessionEnd`.
- Writes commands that run `python -m vauxhall.hooks.codex.telemetry_hook` from
  the isolated environment: shell-quoted on POSIX, and as UTF-16LE
  Base64-encoded PowerShell on Windows, so path metacharacters are not
  interpreted.
- Gives each handler a 3-second timeout; the MQTT connection attempt is limited
  to 1 second. Handlers are synchronous so tool start and completion events stay
  in order.

Codex runs project hooks only after you trust them. Open `/hooks` in Codex,
review the definitions, and trust them.

### Manual Configuration

Add the command handler to each event in `.codex/hooks.json`. For example:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "'/absolute/path/to/.vauxhall-venv/bin/python' -m vauxhall.hooks.codex.telemetry_hook",
            "statusMessage": "Sending Vauxhall telemetry",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

Codex passes one JSON event object on stdin. On Windows, use the installer; it
generates the encoded PowerShell command needed for safe path handling.

## Gemini CLI

### Event Mapping

| Gemini event | Vauxhall state |
| :--- | :--- |
| `BeforeAgent` | `Thinking` (with `prompt`) |
| `AfterModel` | `Thinking` (`Model replied`, with `tokens` and assistant text when reported), after the response's final chunk |
| `BeforeTool` | `Acting`; `Waiting for Input` for `ask_user` |
| `AfterTool` | `Thinking`, `Error`, or `Idle`, based on the tool result |
| `Notification` | `Waiting for Input` for `ToolPermission`; others are ignored |
| `AfterAgent` | `Idle` (`Ready`) |
| `SessionEnd` | `Idle`, with a normalized reason |
| `SessionStart` | `Idle` (`Session started`, `Session resumed`, or `Session cleared`) |
| `PreCompress` | `Compacting context`: `Thinking` for `auto`, `Idle` for `manual` |
| Any other event | Ignored |

`AfterTool` outcomes follow the documented
[Gemini CLI hook](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md)
fields:

| `tool_response` | State | Status |
| :--- | :--- | :--- |
| Cancellation marker (same as Codex) | `Idle` | `cancelled` |
| Non-null `error` | `Error` | `failed` |
| Any other object | `Thinking` | `completed` |
| Missing or not an object | `Thinking` | `result unavailable` |

Gemini CLI has no tool-interrupt field. `SessionEnd` reports `session exited`,
`session cleared`, `logged out`, or `input closed` for the `exit`, `clear`,
`logout`, and `prompt_input_exit` reasons, and `session ended` otherwise. Raw
reason values are not published.

### Published Data

- `BeforeTool` publishes the tool input as JSON in `args`, and a `cmd` value:
  the command for `run_shell_command`, or `file_path` for `read_file`,
  `write_file`, and `replace`. Events whose `args` exceed 4,096
  characters fail validation and are not published.
- `tool_response` content is never published.
- `AfterModel` text chunks are assembled in a private temporary file and
  published when that model response ends, including responses before tool
  calls. `BeforeAgent` discards text left by an unfinished prior response.
  Messages over 4,096 characters end with an ellipsis.
- Each `BeforeTool` records its start time in its own file in the system
  temporary directory, named by workspace, session ID, tool name, and tool
  input. Gemini CLI sends no tool call ID, so `AfterTool` claims the most recent
  start recorded for the same call by renaming its file, and concurrent hooks
  never share a start. A start left by a call that never finished doesn't
  inflate a later duration. Identical calls that overlap each report a
  duration, but they can't be told apart, so they may report each other's.
- `ToolPermission` notifications publish the message, and the tool name only
  for MCP tools (`details.toolName`). Shell commands and file diffs in
  `details` are not published.

### Failure Handling

As with Codex, the hook writes one JSON object to stdout for every input and
sends logs and configuration errors to stderr.

### Automated Installation

After installing `vauxhall[hooks]`, run from the Gemini CLI workspace:

```bash
vauxhall-hook-install gemini
```

The installer:

- Backs up `.gemini/settings.json` to `.gemini/settings.json.bak`. If the file
  is invalid JSON or has an unexpected structure, it exits with an error and
  leaves the file unchanged.
- Recreates `.vauxhall-venv` and installs `vauxhall[hooks]` into it from the
  same source as the running installer: the same Git commit, local directory,
  or wheel file, or otherwise the matching PyPI release. Agents named in one
  command share that environment, so it is built once.
- Removes only handlers that Vauxhall generated: commands with the installed
  hook module invocation, or the named handlers from earlier installers that
  ran `hooks/gemini/telemetry_hook.py` from a checkout. User hooks, including
  ones whose names start with `vauxhall-`, and the `enabled`, `disabled`, and
  `notifications` hook options are kept.
- Registers `vauxhall-thinking` (`BeforeAgent`), `vauxhall-idle`
  (`AfterAgent`), `vauxhall-model` (`AfterModel`), `vauxhall-acting`
  (`BeforeTool`), `vauxhall-done` (`AfterTool`), `vauxhall-waiting`
  (`Notification`), `vauxhall-session-start` (`SessionStart`),
  `vauxhall-compress` (`PreCompress`), and `vauxhall-session-end`
  (`SessionEnd`), and replaces the settings file atomically.
- Writes commands that run `python -m vauxhall.hooks.gemini.telemetry_hook`,
  quoted the same way as the Codex installer.

### Manual Configuration

Add the hook to each event in `.gemini/settings.json`:

```json
{
  "hooks": {
    "BeforeAgent": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "vauxhall-telemetry",
            "type": "command",
            "command": "'/absolute/path/to/.vauxhall-venv/bin/python' -m vauxhall.hooks.gemini.telemetry_hook"
          }
        ]
      }
    ],
    "AfterAgent": [...],
    "AfterModel": [...],
    "BeforeTool": [...],
    "AfterTool": [...],
    "Notification": [...],
    "SessionStart": [...],
    "PreCompress": [...],
    "SessionEnd": [...]
  }
}
```

## Configuration

The dashboard reads `vauxhall_dashboard.json` and hooks read
`vauxhall_hooks.json`, from the current directory or, if the file is not there,
from `~/.config/vauxhall/`. Environment variables override file values, which
override defaults. See [README.md](README.md#configuration) for every field and
environment variable.

Invalid explicit values abort dashboard startup or hook telemetry with an error
naming the source (environment variable or absolute file path), the field, the
value, and the expected constraint. Hooks print that error to stderr and still
write one JSON object to stdout. MQTT authentication and TLS are out of scope
until issue #3.

To change configuration from code, use `vauxhall.core.config_store` rather than
writing JSON directly. `save_user_config` writes only
`~/.config/vauxhall/<filename>`, validates with the unchanged
`DashboardConfig.load` or `HookConfig.load`, and replaces the file atomically.
`field_sources` reports each field's source (`environment`, `file`, or
`default`) and whether it is editable. Fields set by `VAUXHALL_*` environment
variables are read-only, and so is every field when a configuration file exists
in the current directory. Saving a read-only or unknown field, or saving to a
malformed file, raises `ConfigurationError` without writing. See
[README.md](README.md#configuration) for details.

## Development and Maintenance Rules

All contributors, including AI agents, must:

1. **Code style**: Before committing Python changes, run `ruff format .` and
   `ruff check .` with the Ruff version pinned in `pyproject.toml`, and fix every
   error (`ruff check --fix .` fixes many). Every Python file must start with the
   project's SPDX copyright and license headers.
2. **Testing**: All tests must pass before committing.
   - Run `.venv/bin/pytest`. The packaging tests build real wheels, check
     metadata and bundled UI assets, install the wheel into clean environments,
     and run both hook installers outside the source checkout.
   - `.venv/bin/pytest -m packaged` runs the packaged dashboard startup test,
     which is deselected by default because it downloads Qt. CI runs it on
     Linux, macOS, and Windows.
   - With Node.js 20.19 or newer, run `npm test` for the frontend.
   - Add unit tests for every new feature and bug fix.
3. **Documentation**: After every change, update `README.md` (features,
   architecture, usage) and `AGENTS.md` (integration, states, dashboard
   behavior) to match the code.
