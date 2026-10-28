<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Agent Integrations

Vauxhall works with any agent that can publish JSON over MQTT. It ships hooks
for Claude Code, Codex, and Gemini CLI; other agents can use the Python client
or publish messages directly. [privacy.md](privacy.md) summarizes what each
integration publishes and how to limit it.

## Publishing Telemetry

### Python Client

```python
from uuid import uuid4

from vauxhall.core.config import MQTTConfig
from vauxhall.hooks.client import publish

session = {
    "agent": "MyAgent",
    "workspace": "/path/to/project",
    "session_id": str(uuid4()),
}

# Report a running tool with metrics and environment
delivered = publish(
    [
        {
            **session,
            "state": "Acting",
            "env": "local",  # Optional: "local" or "remote"
            "details": {
                "tool": "grep",
                "cmd": "grep -r 'TODO' .",
                "tokens": 1245,  # Optional
                "duration": 12.4,  # Optional, in seconds
            },
        }
    ],
    MQTTConfig(host="localhost", port=1883),
)

# Report that the agent is done, with the hooks' broker settings
publish([{**session, "state": "Idle"}])
```

Each event is the [telemetry schema](#telemetry-schema) without
`schema_version`, which `publish()` adds. It publishes the events at QoS 1
over one connection and waits up to one second in total for the broker's
acknowledgments. Connecting and the TLS handshake each take at most about a
second too: it connects with a 1-second keepalive whatever `mqtt.keepalive`
says, because paho times the TLS handshake with the keepalive rather than
the connection timeout, and the connection lasts only about a second. It returns `True` only when every event is valid and
acknowledged; an invalid event is skipped, and validation, connection, and
publish failures return `False` instead of raising. Without an `MQTTConfig`,
it uses the [hooks' broker settings](configuration.md). Importing the client or
configuration modules does not change the host application's logging; the
dashboard and hook entry points configure logging when they run.

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
variable. If none is available, the hook skips the event. An ID that would
exceed 256 characters is replaced by its SHA-256 hash, keeping the source
prefix (`native-sha256:<hex>`), so it stays stable and distinct.

The built-in hooks also shorten any `details` string over 4,096 characters,
such as a long prompt or command, to its first 4,095 characters and an
ellipsis, so the event is still published. A long shell command, such as a
heredoc that writes a file, therefore publishes its start. Gemini CLI's `args` is the exception: an input too long
to publish is left out, because its start could be a file's contents.

A workspace path over 4,096 characters becomes its first 24 and last 48
characters around an ellipsis, then ` [sha256:<hex>]`, the first 16 hex digits
of the full path's hash, which keeps workspaces that differ only in the middle
on separate cards. Copying it from the card gives this text, not a usable
path.

The dashboard drops messages larger than `max_payload_bytes` (65,536 bytes by
default) before decoding them, and logs and drops malformed or invalid
telemetry. Rejection logs never include payload values. The dashboard and
`publish()` share one validator, `vauxhall.core.telemetry`. `publish()`
writes non-ASCII text as UTF-8 rather than `\u` escapes, which take six
bytes per character, unless the payload holds a lone surrogate.

## Supported States

| State | Card color | Meaning |
| :--- | :--- | :--- |
| `Acting` | 🟢 Green | Running a tool or command |
| `Thinking` | 🟢 Green | Processing or planning |
| `Waiting for Input` | 🟡 Yellow | Waiting for the user |
| `Input Required` | 🟡 Yellow | Same as `Waiting for Input` |
| `Error` | 🔴 Red | A tool or the agent failed |
| `Idle` | None | Finished or on standby |

## Claude Code

### Event Mapping

| Claude Code event | Vauxhall state |
| :--- | :--- |
| `SessionStart` | `Idle`, with a normalized source; ignored after compaction |
| `UserPromptSubmit` | `Thinking` (with `prompt`) |
| `PreToolUse` | `Acting`; `Waiting for Input` for `AskUserQuestion` |
| `PermissionRequest` | `Waiting for Input` |
| `PermissionDenied` | `Thinking` (`denied`, `Denied by auto mode`) |
| `PostToolUse` | `Thinking` (`completed`); `Idle` (`cancelled`) when interrupted |
| `PostToolUseFailure` | `Error` (`failed`); `Idle` (`cancelled`) for `is_interrupt` |
| `Elicitation` | `Waiting for Input` (with the MCP server's message) |
| `ElicitationResult` | `Acting` (`Input accepted`, `declined`, or `cancelled`) |
| `Notification` | `Waiting for Input` for `permission_prompt`, `idle_prompt`, `elicitation_dialog`, `elicitation_url_dialog`, and `quota_auto_resume_stale`; `Thinking` (`Resumed after usage limit`) for `quota_auto_resume_fired`; `Idle` (`Stopped waiting for usage limit`) for `quota_auto_resume_disabled`; others are ignored |
| `MessageDisplay` | `Thinking` with the completed assistant message |
| `SubagentStart` | `Acting` (`tool` is `Agent`, `cmd` is the agent type) |
| `PreCompact` | `Thinking` (`Compacting context`, with the trigger) |
| `PostCompact` | `Context compacted`: `Idle` after `manual`, `Thinking` after `auto` |
| `Stop` | `Idle` (`Ready`, with `last_assistant_message` when available) |
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

`PermissionDenied` fires only in auto mode. The model receives the denial and
continues, so the state is `Thinking`, not `Error`, and no duration is
reported because the tool never ran. `Elicitation` fires as soon as an MCP
server asks for input; the `elicitation_dialog` notification follows only
after about six seconds without typing. `ElicitationResult` does not fire when
another hook answered the elicitation; the card then waits until the MCP
tool's `PostToolUse`. Vauxhall's hook prints `{}`, which leaves every
elicitation to the user.

Some signals are intentionally absent:

- `SubagentStop` is not registered. For a foreground subagent, `PostToolUse`
  for the `Agent` tool already reports completion; for a background subagent,
  it would mark an idle session as working.
- `TeammateIdle` and the `agent_needs_input` and `agent_completed`
  notifications describe other sessions, so they are ignored for the same
  reason.
- `PostToolBatch` is not registered: `PostToolUse` already reports each call
  in the batch.
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
  For `PermissionDenied`, the denial `reason` is not published.
- `Elicitation` publishes the MCP server's `message` as the prompt, but not
  its `url` or `requested_schema`. `ElicitationResult` publishes only the
  action, never the submitted `content`. The usage-limit notifications publish
  fixed statuses, except `quota_auto_resume_stale`, which publishes its
  message as the prompt like other waiting notifications.
- Each `MessageDisplay` batch is kept in its own private temporary file, so
  hooks running at once don't lose each other's text. The batches are
  assembled and published when the message ends, including messages shown
  during a turn, and the files are then removed. Claude Code runs the final message's
  `MessageDisplay` and `Stop` hooks at the same time, so that `Thinking`
  event can arrive after `Stop`; the dashboard ignores it when it only
  repeats the message `Stop` published. Messages longer than 4,096 characters end with
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

- Backs up `.claude/settings.local.json` to `.claude/settings.local.json.bak`. Without that file, the backup holds `{}`.
  An existing backup is kept, so a reinstall doesn't lose the original
  settings. If the file is invalid JSON or has an unexpected structure, it exits with an
  error and leaves the file unchanged.
- Recreates `.vauxhall-venv` and installs `vauxhall[hooks]` into it from the
  same source as the running installer: the same Git commit, local directory,
  or wheel file, or otherwise the matching PyPI release. Agents named in one
  command share that environment, so it is built once. If building it fails,
  the installer shows pip's error, restores the previous environment if
  there was one, and changes no settings. If an earlier install was interrupted, it first
  puts back the environment that install set aside, when its own was left
  incomplete, and removes the copy otherwise.
- Replaces existing Vauxhall handlers, keeps all other settings, registers
  every event above, and replaces the settings file atomically. It uses local
  settings because the command contains a machine-specific path.
- Writes commands that run `python -P -m vauxhall.hooks.claude.telemetry_hook`,
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
            "command": "'/absolute/path/to/.vauxhall-venv/bin/python' -P -m vauxhall.hooks.claude.telemetry_hook",
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
  system temporary directory and limits each read to 1 MiB. One hook reads at
  a time: a hook that runs while another reads publishes no commentary, and
  a later hook in the same turn publishes it. Messages over
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

- Backs up `.codex/hooks.json` to `.codex/hooks.json.bak`. Without that file, the backup holds `{}`. An existing
  backup is kept, so a reinstall doesn't lose the original settings. If the
  file is invalid JSON or has an unexpected structure, it exits with an error and leaves
  the file unchanged.
- Recreates `.vauxhall-venv` and installs `vauxhall[hooks]` into it from the
  same source as the running installer: the same Git commit, local directory,
  or wheel file, or otherwise the matching PyPI release. Agents named in one
  command share that environment, so it is built once. If building it fails,
  the installer shows pip's error, restores the previous environment if
  there was one, and changes no settings. If an earlier install was interrupted, it first
  puts back the environment that install set aside, when its own was left
  incomplete, and removes the copy otherwise.
- Replaces existing Vauxhall handlers, keeps all other configuration, and
  registers `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
  `PermissionRequest`, `PostToolUse`, `SubagentStart`, `PreCompact`,
  `PostCompact`, `Stop`, `Interrupt`, and `SessionEnd`.
- Writes commands that run `python -P -m vauxhall.hooks.codex.telemetry_hook`
  from the isolated environment: shell-quoted on POSIX, and as UTF-16LE
  Base64-encoded PowerShell on Windows, so path metacharacters are not
  interpreted. `-P` keeps the workspace off `sys.path`: the agent runs hooks
  there, and without it a repository's own `vauxhall` package would run in
  place of the installed hooks. Handlers written without `-P` are still
  recognized, so a reinstall replaces them.
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
            "command": "'/absolute/path/to/.vauxhall-venv/bin/python' -P -m vauxhall.hooks.codex.telemetry_hook",
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
  `write_file`, and `replace`. When the JSON exceeds 4,096 characters, `args`
  is left out and the event is published without it.
- `tool_response` content is never published.
- Each `AfterModel` text chunk is kept in its own private temporary file, so
  hooks running at once don't lose each other's text. The chunks are
  assembled and published when that model response ends, including responses before tool
  calls. `BeforeAgent` discards text left by an unfinished prior response.
  Messages over 4,096 characters end with an ellipsis.
- Each `BeforeTool` records its start time in its own file in the system
  temporary directory, named by workspace, session ID, tool name, and tool
  input. Gemini CLI sends no tool call ID, so `AfterTool` claims the most recent
  start recorded for the same call by renaming its file, and concurrent hooks
  never share a start. A start left by a call that never finished doesn't
  inflate a later duration, and starts older than 24 hours are removed, so a
  call that runs longer reports no duration. Identical calls that overlap
  each report a duration, but they can't be told apart, so they may report
  each other's.
- `ToolPermission` notifications publish the message, and the tool name only
  for MCP tools (`details.toolName`). Shell commands and file diffs in
  `details` are not published.

### Failure Handling

As with Codex, the hook writes one JSON object to stdout for every input and
sends logs and configuration errors to stderr. Its MQTT connection attempt is
limited to 1 second.

### Automated Installation

After installing `vauxhall[hooks]`, run from the Gemini CLI workspace:

```bash
vauxhall-hook-install gemini
```

The installer:

- Backs up `.gemini/settings.json` to `.gemini/settings.json.bak`. Without that file, the backup holds `{}`. An existing
  backup is kept, so a reinstall doesn't lose the original settings. If the
  file is invalid JSON or has an unexpected structure, it exits with an error and
  leaves the file unchanged.
- Recreates `.vauxhall-venv` and installs `vauxhall[hooks]` into it from the
  same source as the running installer: the same Git commit, local directory,
  or wheel file, or otherwise the matching PyPI release. Agents named in one
  command share that environment, so it is built once. If building it fails,
  the installer shows pip's error, restores the previous environment if
  there was one, and changes no settings. If an earlier install was interrupted, it first
  puts back the environment that install set aside, when its own was left
  incomplete, and removes the copy otherwise.
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
- Writes commands that run `python -P -m vauxhall.hooks.gemini.telemetry_hook`,
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
            "command": "'/absolute/path/to/.vauxhall-venv/bin/python' -P -m vauxhall.hooks.gemini.telemetry_hook"
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
