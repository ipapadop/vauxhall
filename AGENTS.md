# Agent Integration Guide

Vauxhall is designed to be agent-agnostic. You can integrate any AI agent or CLI tool by sending telemetry messages to the MQTT broker.

## Supported Agents

Currently, Vauxhall includes built-in support or templates for:
- **Codex**: Full lifecycle, tool, permission, and turn-completion hooks.
- **Gemini CLI**: Full pre/post command hooks.
- **Generic Agents**: Any agent can be simulated or integrated using the `TelemetryClient`.

## Integration Methods

### 1. Using Python Hooks (Recommended)
If your agent supports Python-based hooks or you are wrapping a CLI tool in Python, use the `TelemetryClient`.

```python
from uuid import uuid4

from vauxhall.hooks.client import TelemetryClient

session_id = str(uuid4())
client = TelemetryClient(host="localhost", port=1883)

# Send an "Acting" state with tool details, metrics, and environment context
delivered = client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    session_id=session_id,
    state="Acting",
    env="local",  # Optional: "local" or "remote"
    tool="grep",
    cmd="grep -r 'TODO' .",
    tokens=1245,  # Optional: Token count for the operation
    duration=12.4,  # Optional: Duration in seconds
)

# Send an "Idle" state when finished
client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    session_id=session_id,
    state="Idle",
)
```

`send()` publishes at QoS 1 and returns `True` only when MQTT receives the broker's acknowledgment. It waits up to one second for that acknowledgment and returns `False`, without raising, when serialization, connection, or publication fails. Use `TelemetryClient` as a context manager when sending several events so they share one connection. Importing the client and configuration modules does not configure or replace the host application's root logging; dashboard and hook entry points configure Vauxhall logging when they run.

### 2. Manual MQTT (Any Language)
You can publish JSON messages to the following topic structure:
`vauxhall/agents/<agent_name>/activity`

**Message Format:**
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

Optional `env` and operation values such as `tool`, `cmd`, `tokens`,
`duration`, `prompt`, and `error` may also be sent; operation values belong in
the `details` object.

## Telemetry schema

Version 1 is the only accepted telemetry schema. The `schema_version`, `agent`,
`workspace`, `session_id`, and `state` fields are required. `session_id` is
opaque, must remain stable throughout one session, and must be unique among
concurrent sessions for the same agent and workspace. Generic producers should
generate one UUID at session startup and pass it on every event.

The built-in hooks resolve a session ID from the agent's native ID first, then
from a hash of its transcript path, and finally from `VAUXHALL_SESSION_ID`. If
none is available, the hook skips the event. The dashboard logs and drops
unversioned, incomplete, and unsupported payloads.

## Supported States & UI Indicators

The dashboard uses the `state` field to color-code agent cards:

| State | UI Color | Description |
| :--- | :--- | :--- |
| `Acting` | 🟢 Green | Agent is currently executing a tool or command. |
| `Thinking` | 🟢 Green | Agent is processing or planning. |
| `Waiting for Input` | 🟡 Yellow | Agent is paused and waiting for user confirmation. |
| `Input Required` | 🟡 Yellow | Same as above. |
| `Error` | 🔴 Red | Agent encountered a fatal error. |
| `Idle` | None | Agent is finished or standby. |

## Metadata & Features

Dashboard cards are identified by the combination of `agent`, `workspace`, and
`session_id`. Separate sessions therefore create separate cards even when the
agent name and workspace are identical.

### Environment Badges
Vauxhall displays a badge (LOCAL, REMOTE) based on the `env` field. If omitted, the dashboard attempts to guess the environment based on the `workspace` path:
- Paths starting with `/home` or `C:\` default to **LOCAL**.
- Other absolute paths default to **REMOTE**.

If `tokens` or `duration` are provided in the `details` object, they will appear as small badges in the **card footer**.

### Real-Time Activity Log
The `log-area` on each card is a real-time append-only stream of the **last 5 events**. Any update containing a `tool`, `cmd`, or `prompt` will append a new line with a timestamp (`[HH:mm:ss]`).

- **Acting**: Shows "Running: <tool> <cmd>".
- **Waiting**: Shows "Prompt: <prompt>" (prioritized over tool names).
- **Thinking**: Shows "Completed: <tool>" or the specific status message.

This area is non-scrolling to keep the dashboard clean.

All values received through telemetry are treated as untrusted text and must not be inserted into executable HTML.

Clicking an agent card copies the raw `workspace` value to the clipboard. The dashboard must not concatenate this untrusted value into a shell command.

### Session History & Audit
The dashboard automatically maintains the last 20 operations per agent. It retains up to 100 active cards by default; when a new identity arrives at capacity, the least-recently-seen card is evicted. Users can view a card's history by clicking the **Clock (🕒)** icon in the card footer to open a **resizable modal**. This modal supports real-time updates and includes a "smart auto-scroll" that freezes when you are hovering to allow for easy inspection.

## Specific Agent Instructions

### Codex

Vauxhall provides a unified Codex command hook for lifecycle events, tool executions, permission requests, and turn completion. It maps Codex events as follows:

| Codex event | Vauxhall state |
| :--- | :--- |
| `SessionStart`, `UserPromptSubmit` | `Thinking` |
| `PreToolUse` | `Acting` |
| `PermissionRequest` and `request_user_input` | `Waiting for Input` |
| `PostToolUse` | `Thinking`, `Error`, or `Idle`, based on the tool result |
| `Stop`, `SessionEnd` | `Idle` (`Ready`) |
| `Interrupt` | `Idle` (`interrupted`) |

Tool outcomes follow the documented [Codex hooks](https://developers.openai.com/codex/hooks/) result fields:

| Integration | Success evidence | Failure evidence | Cancellation evidence | Interruption evidence |
| :--- | :--- | :--- | :--- | :--- |
| Codex | tool-specific `tool_response.exit_code == 0` or `isError == false` | non-zero `exit_code` or `isError == true` | structured cancellation marker when supplied by a tool | `Interrupt` hook event |
| Gemini | `tool_response` object with no `error` | non-null `tool_response.error` | structured cancellation marker inside response/error | no tool-interrupt field; `SessionEnd.reason` covers CLI exit/clear/logout/input exit |

Arbitrary `tool_response` content is never sent as telemetry. Unknown or malformed result shapes use `result unavailable` rather than claiming success.

Telemetry is best-effort. The hook lazy-loads telemetry and configures logging inside its failure boundary, then reserves stdout for one JSON object, including for unknown events, malformed input, and telemetry failures, so monitoring cannot interrupt Codex. Logs go to stderr. Tool durations use per-invocation timing files so concurrent tool calls do not overwrite one another. Only canonical `Bash` tools publish their command text; patch contents and arbitrary MCP or local-tool input fields are not published.

The hook preserves Codex's native session identity, so separate native Codex
sessions in one workspace create separate dashboard cards. If no native ID is
available, it uses the shared fallback chain described in
[Telemetry schema](#telemetry-schema) and skips events that have no stable
session identity.

Gemini tool-duration timing files are keyed by the resolved session identity
and, when present, `tool_call_id`. This prevents concurrent sessions in one
workspace from overwriting each other's start times and also separates
concurrent tool calls within a session when Gemini supplies an invocation ID.

#### Automated Installation (Recommended)

After installing `vauxhall[hooks]`, run this command from the Codex workspace:

```bash
vauxhall-install-codex
```

The installer refreshes `.vauxhall-venv`, installs the exact immutable
`vauxhall[hooks]` release that supplied the command, preserves unrelated
configuration in `.codex/hooks.json`, replaces existing Vauxhall Codex
handlers, and registers `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `PostToolUse`, `Stop`, `Interrupt`, and `SessionEnd`.
Existing invalid JSON or nested hook structure is backed up and left unchanged.
Hook commands execute `python -m vauxhall.hooks.codex.telemetry_hook` from the
isolated environment. They use shell quoting on POSIX and UTF-16LE
Base64-encoded PowerShell on Windows so workspace-path metacharacters are not
interpreted by the shell. Each handler has an explicit three-second timeout,
and MQTT connection setup is limited to one second; handlers remain synchronous
so tool-start and tool-completion telemetry retain lifecycle order. The
installed hooks do not depend on the checkout from which Vauxhall was built.

Project hooks require trust before Codex runs them. Open `/hooks` in Codex after installation, review the definitions, and trust them.

#### Manual Configuration

Add the command handler to each desired event in `.codex/hooks.json`. For example:

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

Codex passes one JSON event object on stdin. The hook reads `cwd`, `hook_event_name`, tool metadata, prompt text, and permission descriptions, then publishes the corresponding Vauxhall telemetry event.

On Windows, use the automated installer rather than adapting the POSIX command above; it generates the encoded PowerShell command required for safe path handling.

## Configuration

Dashboard settings load from `vauxhall_dashboard.json` in the current working
directory, then `~/.config/vauxhall/`; hook settings use
`vauxhall_hooks.json` in the same paths. Environment variables override file
values, which override dataclass defaults. The dashboard exposes
`VAUXHALL_DASHBOARD_PORT`, `VAUXHALL_DASHBOARD_DEBUG`,
`VAUXHALL_DASHBOARD_WINDOW_TITLE`, `VAUXHALL_DASHBOARD_WIDTH`,
`VAUXHALL_DASHBOARD_HEIGHT`, `VAUXHALL_DASHBOARD_STALE_THRESHOLD`,
`VAUXHALL_DASHBOARD_PENDING_UPDATE_LIMIT`,
`VAUXHALL_DASHBOARD_MAX_ACTIVE_AGENTS`, and
`VAUXHALL_DASHBOARD_MAX_PAYLOAD_BYTES`. MQTT and logging settings are shared:
`VAUXHALL_MQTT_HOST`, `VAUXHALL_MQTT_PORT`,
`VAUXHALL_MQTT_KEEPALIVE`, and `VAUXHALL_LOGGING_LEVEL`.

Explicit values are strictly validated. Malformed JSON, non-object sections,
wrong scalar types, invalid ranges, and invalid environment values abort
dashboard startup or hook initialization with a source-aware error naming the
environment variable or absolute file path, logical field, invalid value, and
expected constraint. MQTT authentication and TLS fields remain out of scope
until issue #3.

## Dashboard Telemetry Ingress Limits

The dashboard drops MQTT payloads larger than
`VAUXHALL_DASHBOARD_MAX_PAYLOAD_BYTES` (65,536 bytes by default) before
decoding JSON, and drops malformed or unsupported telemetry after decoding.
Accepted telemetry uses schema version 1: non-empty `agent` (128 characters),
`workspace` (4,096), `session_id` (256), and one supported `state` (32), with
optional `env` (`local` or `remote`, 16). `details` allows up to 16 string keys
of 64 characters and scalar values; string values are capped at 4,096
characters. Numeric metrics such as `tokens` and `duration` must be numbers,
not booleans.

The shared `vauxhall.core.telemetry` validator enforces these schema and field
limits for dashboard ingestion and the built-in telemetry client. Rejection
reasons never include payload values.

Before the frontend is ready, the dashboard retains only the newest
`VAUXHALL_DASHBOARD_PENDING_UPDATE_LIMIT` events (500 by default); each full
buffer insertion discards the oldest event. Discard warnings are rate-limited
at power-of-two discard counts and never include telemetry contents.

## Dashboard Connection Lifecycle

The dashboard reports `Connecting...`, `Connected to Agent Fleet`, retrying
connection failures or disconnects, and `Disconnected` for intentional
shutdown. It stops the MQTT client exactly once when the UI loop exits,
including after an exception or partial startup failure. The dashboard extra
requires Pyloid 0.27.2 or newer. Its `BrowserWindow` wrapper marshals
cross-thread commands through `command_signal` and `_handle_command`, allowing
MQTT callbacks to call `window.invoke()` directly without a second queue;
Vauxhall does not use those private symbols at runtime.

### Gemini CLI

Vauxhall provides a unified telemetry hook for Gemini CLI that handles agent lifecycle events, tool executions, and user notifications. It implements documented [Gemini CLI hook](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md) fields, including `AfterTool.tool_response` and `SessionEnd.reason`. A session end reports one of `session exited`, `session cleared`, `logged out`, `input closed`, or the conservative fallback `session ended`; raw reason values are not published.

Telemetry is best-effort: the hook configures logging inside its failure boundary and always exits normally with one JSON object on stdout, including for ignored events, malformed input, and telemetry failures. Logs go to stderr so monitoring cannot corrupt the Gemini CLI hook protocol.

The hook preserves Gemini's native session identity, so separate native Gemini
sessions in one workspace create separate dashboard cards. If no native ID is
available, it uses the shared fallback chain described in
[Telemetry schema](#telemetry-schema) and skips events that have no stable
session identity.

#### Automated Installation (Recommended)
After installing `vauxhall[hooks]`, register the hooks in the current Gemini
workspace by running:

```bash
vauxhall-install-gemini
```

This script will:
1.  **Isolated Environment**: Create a dedicated virtual environment (`.vauxhall-venv`) in the current directory to isolate telemetry dependencies. If the directory exists, it is refreshed.
2.  **Dependency Management**: Install the exact immutable `vauxhall[hooks]` release that supplied the command into the isolated venv.
3.  **Clean Installation**: Purge any existing hooks starting with `vauxhall-` to ensure a clean state before registering new ones.
4.  **Configuration**: Locate (or create) `.gemini/settings.json` in your workspace and register `python -m vauxhall.hooks.gemini.telemetry_hook` using the absolute path to the isolated venv's Python interpreter.
5.  **Descriptive Hooks**: Setup hooks with specific names (`vauxhall-thinking`, `vauxhall-acting`, `vauxhall-session-end`, etc.) and clear descriptions for easy identification.

The generated hooks are independent of the checkout from which Vauxhall was
built. POSIX paths are shell-quoted, and Windows commands use UTF-16LE
Base64-encoded PowerShell so path metacharacters are not interpreted.

#### Manual Configuration
If you prefer to configure it manually, add the following to your `.gemini/settings.json`:

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
    "BeforeTool": [...],
    "AfterTool": [...],
    "Notification": [...]
  }
}
```

## Development & Maintenance Rules

To ensure the stability and readability of the Vauxhall ecosystem, all contributors (and AI agents) must follow these rules:

1.  **Code Style**: Before committing any Python changes, you MUST run:
    - `ruff format .` to ensure consistent formatting.
    - `ruff check .` to identify potential issues.
    - All `ruff check` errors must be resolved or fixed using `ruff check --fix .`.
    - Every Python file must begin with the project's SPDX copyright and license headers.
    - Use the exact Ruff version declared by the project so local and CI results agree.
3.  **Testing**: Before committing, all existing and new tests MUST pass.
    - Run `.venv/bin/pytest` to verify.
    - With Node.js 20.19 or newer, run `npm test` to verify frontend rendering behavior.
    - Always add unit tests for new features or bug fixes.
    - The packaging tests build real wheels, verify metadata and dashboard UI assets, install the wheel into clean environments, and run both public hook installers outside the source checkout.
4.  **Documentation Synchronization**: After **every** code change or feature implementation, you MUST review and update the following files to reflect the current state of the project:
    - `README.md`: Update features, architecture, and usage instructions.
    - `AGENTS.md`: Update integration methods, states, and metadata features.
