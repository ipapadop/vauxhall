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
from vauxhall.hooks.client import TelemetryClient

client = TelemetryClient(host="localhost", port=1883)

# Send an "Acting" state with tool details, metrics, and environment context
delivered = client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    state="Acting",
    env="local",  # Optional: "local" or "remote"
    tool="grep",
    cmd="grep -r 'TODO' .",
    tokens=1245,  # Optional: Token count for the operation
    duration=12.4,  # Optional: Duration in seconds
)

# Send an "Idle" state when finished
client.send("MyAgent", "/path/to/project", "Idle")
```

`send()` publishes at QoS 1 and returns `True` only when MQTT receives the broker's acknowledgment. It waits up to one second for that acknowledgment and returns `False`, without raising, when serialization, connection, or publication fails. Use `TelemetryClient` as a context manager when sending several events so they share one connection. Importing the client and configuration modules does not configure or replace the host application's root logging; dashboard and hook entry points configure Vauxhall logging when they run.

### 2. Manual MQTT (Any Language)
You can publish JSON messages to the following topic structure:
`vauxhall/agents/<agent_name>/activity`

**Message Format:**
```json
{
  "agent": "AgentName",
  "workspace": "/absolute/path/to/workspace",
  "state": "Acting", 
  "env": "remote", 
  "details": {
    "tool": "tool_name",
    "cmd": "command executed",
    "tokens": 1234,
    "duration": 5.2,
    "prompt": "User prompt if waiting",
    "error": "Error message if failed"
  }
}
```

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
The dashboard automatically maintains a full buffer of the last 20 operations per agent. Users can view this history by clicking the **Clock (🕒)** icon in the card footer to open a **resizable modal**. This modal supports real-time updates and includes a "smart auto-scroll" that freezes when you are hovering to allow for easy inspection.

## Specific Agent Instructions

### Codex

Vauxhall provides a unified Codex command hook for lifecycle events, tool executions, permission requests, and turn completion. It maps Codex events as follows:

| Codex event | Vauxhall state |
| :--- | :--- |
| `SessionStart`, `UserPromptSubmit` | `Thinking` |
| `PreToolUse` | `Acting` |
| `PermissionRequest` and `request_user_input` | `Waiting for Input` |
| `PostToolUse` | `Thinking` |
| `Stop`, `Interrupt`, `SessionEnd` | `Idle` |

Telemetry is best-effort. The hook lazy-loads telemetry and configures logging inside its failure boundary, then reserves stdout for one JSON object, including for unknown events, malformed input, and telemetry failures, so monitoring cannot interrupt Codex. Logs go to stderr. Tool durations use per-invocation timing files so concurrent tool calls do not overwrite one another. Only canonical `Bash` tools publish their command text; patch contents and arbitrary MCP or local-tool input fields are not published.

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

### Gemini CLI

Vauxhall provides a unified telemetry hook for Gemini CLI that handles agent lifecycle events, tool executions, and user notifications.

Telemetry is best-effort: the hook configures logging inside its failure boundary and always exits normally with one JSON object on stdout, including for ignored events, malformed input, and telemetry failures. Logs go to stderr so monitoring cannot corrupt the Gemini CLI hook protocol.

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
5.  **Descriptive Hooks**: Setup hooks with specific names (`vauxhall-thinking`, `vauxhall-acting`, etc.) and clear descriptions for easy identification.

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
