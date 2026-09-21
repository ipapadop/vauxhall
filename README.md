<p align="center">
  <a href="https://github.com/ipapadop/vauxhall">
    <img src="vauxhall/dashboard/ui/logo.svg" width="150" alt="Vauxhall Logo">
  </a>
</p>

# Vauxhall Agent Dashboard

Vauxhall is a real-time dashboard for agents such as Claude Code,
Codex, and Gemini CLI. Agents publish telemetry over MQTT, and the dashboard
shows each agent session as a card in a grid.

## Features

- **Live state**: Cards are color-coded by state: Acting, Thinking, Waiting for
  Input, Input Required, Error, or Idle.
- **Session-aware cards**: Cards are keyed by agent, workspace, and session ID,
  so concurrent sessions in one workspace stay separate. Up to 100 cards are
  kept by default; a new session evicts the least recently seen card.
- **Activity log**: Each card shows its last 5 events, including agent messages,
  with `[HH:mm:ss]`
  timestamps, token and duration badges for the latest operation, and a LOCAL
  or REMOTE badge.
- **History**: The 🕒 icon opens a resizable modal with the card's last 20
  events. It updates live, can be filtered, and pauses auto-scroll while you
  hover.
- **Search and sort**: Filter cards by agent name or workspace path, and sort by
  name, recent activity, status, or latest token count.
- **Stale detection**: Cards show a "last seen" timer and turn gray after the
  stale threshold (120 seconds by default). **Clear Stale** removes them.
- **Copy workspace**: Clicking a card copies its raw workspace path.
- **Settings**: The ⚙️ button opens a settings dialog that saves to
  `~/.config/vauxhall/`, applies most changes without a restart, and can also
  update the hooks configuration.
- **Remembered view**: The theme, sort order, history state filter, and window
  size, position, and maximized state are restored the next time the dashboard
  starts.
- **Claude Code, Codex, and Gemini CLI hooks**: Installers register hooks that
  report prompts, assistant messages, tool activity, permission waits, tool
  outcomes (completed, failed, cancelled, or result unavailable), and idle
  state. Tool results are never published. Messages are limited to 4,096
  characters per event; longer messages end with an ellipsis.
- **Safe handling**: Telemetry is validated and size-limited, rendered as text,
  and never turned into shell commands. Hooks always return valid protocol JSON,
  even when telemetry fails.

## Architecture

1. **Hooks (producers)**: Python modules run by agent hook events publish
   telemetry to an MQTT broker.
2. **Mosquitto (broker)**: Routes telemetry from hooks to the dashboard.
3. **Dashboard (consumer)**: A Pyloid desktop app with a Python MQTT backend and
   a vanilla JavaScript frontend.

```mermaid
flowchart LR
    subgraph agents["Agent machine"]
        cc["Claude Code"]
        cx["Codex"]
        gm["Gemini CLI"]
        hook["Hook process<br>(.vauxhall-venv)"]
        client["TelemetryClient"]
        cc --> hook
        cx --> hook
        gm --> hook
        hook --> client
    end

    broker["Mosquitto broker"]

    subgraph dashboard["Dashboard (Pyloid desktop app)"]
        sub["DashboardSubscriber"]
        app["DashboardApp"]
        ipc["DashboardIPC"]
        ui["JavaScript UI<br>(card grid, history)"]
        sub -- "valid telemetry" --> app
        app -- "agent-update" --> ui
        ui -- "settings, view state" --> ipc
        ipc --> app
    end

    core["vauxhall.core<br>(schema validation, config, logging)"]

    client -- "publish QoS 1<br>vauxhall/agents/{agent}/activity" --> broker
    broker -- "subscribe<br>vauxhall/agents/+/activity" --> sub

    core -.-> client
    core -.-> sub
```

Both sides share `vauxhall.core`, so hooks and the dashboard validate the same
schema and read configuration the same way.

## Information Flow

```mermaid
sequenceDiagram
    participant A as Agent
    participant H as Hook process
    participant B as Mosquitto
    participant S as DashboardSubscriber
    participant D as DashboardApp
    participant U as JavaScript UI

    A->>H: Hook event as JSON on stdin
    H->>H: Map event to a state, details, and session ID
    H->>B: Publish validated telemetry (QoS 1)
    B-->>H: Acknowledgment (awaited up to 1 second)
    H-->>A: Protocol JSON on stdout
    B->>S: Deliver on vauxhall/agents/+/activity
    S->>S: Drop oversized, malformed, or invalid messages
    S->>D: Valid telemetry
    D->>U: agent-update event
    U->>U: Create or update the card and its history
```

1. **The agent runs a hook.** On each event the agent runs the registered
   command from the workspace's `.vauxhall-venv` and writes the event to its
   stdin.
2. **The hook builds telemetry.** It maps the event to a state (`Acting`,
   `Thinking`, `Waiting for Input`, `Error`, or `Idle`) and details such as
   `tool`, `cmd`, `prompt`, `message`, `status`, `tokens`, and `duration`, and
   resolves the session ID from the agent's own session ID, a hash of the
   transcript path, or `VAUXHALL_SESSION_ID`. Without a session ID the event is
   skipped.
3. **The client publishes it.** `TelemetryClient` validates the payload against
   schema version 1, publishes it at QoS 1 to
   `vauxhall/agents/<agent_name>/activity`, and waits up to one second for the
   broker's acknowledgment. The hook always writes valid protocol JSON on
   stdout, even when telemetry fails, so the agent is never blocked.
4. **The broker routes it.** Mosquitto delivers the message to the dashboard,
   which subscribes to `vauxhall/agents/+/activity`.
5. **The subscriber filters it.** `DashboardSubscriber` drops messages larger
   than `max_payload_bytes`, then those that fail JSON decoding or validation,
   and logs each drop without payload values.
6. **The backend dispatches it.** `DashboardApp` forwards the event to the
   window. Until the frontend signals readiness, events are queued, keeping the
   newest `pending_update_limit` of them; the queue is drained in order when the
   frontend becomes ready.
7. **The frontend renders it.** The UI keys the card by agent, workspace, and
   session ID, creates it if needed (evicting the least recently seen card at
   `max_active_agents`), then updates its state color, activity log, metric
   badges, last-seen timer, and open history modal, and re-applies the current
   search and sort.

Information also flows the other way, from the UI to the backend over
`DashboardIPC`: reading settings and view state, saving them, and copying a
workspace path. Saved settings that change the broker restart the subscriber,
and the backend pushes the new stale threshold and card limit back to the UI.

## Requirements

- Python 3.10, 3.11, 3.12, or 3.13
- Mosquitto MQTT broker (for example, `brew install mosquitto` or
  `sudo apt install mosquitto`)

### Supported platforms

Vauxhall is tested on Linux, macOS, and Windows. CI runs the full test suite
on every supported Python version on Linux, and on Python 3.13 on macOS and
Windows. It also installs the built wheel outside the checkout and starts the
packaged dashboard on all three operating systems.

| | Dashboard | Hooks |
| --- | --- | --- |
| Python | 3.10 - 3.13 | 3.10 - 3.13 |
| Linux | glibc 2.28+ on x86-64, glibc 2.39+ on ARM64 | any |
| macOS | 12 or newer, Intel or Apple silicon | any |
| Windows | 10 or newer, x86-64 or ARM64 | any |

The hooks depend only on `paho-mqtt`, which is pure Python, so they run
anywhere a supported Python does. The dashboard's reach is narrower because
`pyloid` pins `pyside6==6.9.2`, which ships binary wheels only for the
platforms above.

### Explicitly unsupported

- **Python 3.9 and older**: the code uses syntax and standard-library
  behavior introduced in 3.10.
- **Python 3.14 and newer**: `pyloid` declares `Requires-Python: <3.14`, and
  its pinned `pyside6==6.9.2` does the same, so the dashboard cannot be
  installed. The cap is on the whole package rather than the `dashboard`
  extra, so `pip` rejects the install with a clear `Requires-Python` message
  instead of a dependency-resolution trace. The cap will be lifted once
  `pyloid` supports a newer PySide6.
- **musl-based Linux** (Alpine and similar), **32-bit** platforms, and
  **BSD**: PySide6 publishes no wheels for them, so the dashboard cannot be
  installed. Hooks still work if a supported Python is available.

## Installation

Vauxhall isn't published on PyPI yet. Install it from GitHub with pip, which
needs Git on the machine.

Dashboard:

```bash
pip install "vauxhall[dashboard] @ git+https://github.com/ipapadop/vauxhall.git"
```

Agent machines (installs only `paho-mqtt`):

```bash
pip install "vauxhall[hooks] @ git+https://github.com/ipapadop/vauxhall.git"
```

To install a specific branch, tag, or commit, add `@<ref>` to the URL, for
example `git+https://github.com/ipapadop/vauxhall.git@main`.

To install from a local clone instead:

```bash
git clone https://github.com/ipapadop/vauxhall.git
cd vauxhall
pip install ".[dashboard]"  # or ".[hooks]" on agent machines
```

## Usage

### 1. Start the broker

```bash
mosquitto
```

### 2. Run the dashboard

```bash
vauxhall
```

From a source checkout, run `uv run vauxhall`.

### 3. Install agent hooks

Run the installer from the agent's workspace, naming each agent to install:

```bash
# One agent
vauxhall-hook-install claude

# Several agents at once, sharing one hooks environment
vauxhall-hook-install claude codex gemini
```

The agents are `claude`, `codex`, and `gemini`; at least one is required.

The installer recreates `.vauxhall-venv` in the workspace and installs
Vauxhall into it from the same source as the running copy: the same Git
commit, local directory, or wheel file, or otherwise the matching PyPI
release. Agents named in one command share that environment, so it is built
once however many you install. It then registers hooks that run the installed
hook module, so the hooks don't run code from a source checkout. Before
changing an existing hook or settings file, the installer backs it up and
validates it. Every named agent's settings are validated before the
environment is built, so an invalid file leaves them all unchanged and exits
with an error. Reinstalling replaces only Vauxhall's own handlers and writes
each file atomically, preserving unrelated settings and hooks. For Claude Code
the installer writes `.claude/settings.local.json`; restart Claude Code or open
`/hooks` to apply the hooks. For Codex, open `/hooks` after installing to
review and trust the new project hooks.

Run the installer again to enable assistant messages in existing workspaces.
Claude Code and Gemini CLI report completed messages during a turn. Codex
reports its final reply from the `Stop` hook and reads interim commentary from
its local session record when a later hook runs. Codex interim messages are
best effort because the record format can change and writes may lag hook events.

See [AGENTS.md](AGENTS.md) for event mappings, manual configuration, and
integrating other agents.

### 4. Simulate agents

To try the dashboard without real agents, publish mock telemetry from a source
checkout:

```bash
uv run python scripts/simulate_agent.py -n 5 -t 20
```

- `-n`, `--num-agents`: Number of concurrent agents (default 1).
- `-t`, `--num-transitions`: Events per agent (default 5).

## Configuration

The dashboard reads `vauxhall_dashboard.json` and hooks read
`vauxhall_hooks.json`, from the current directory or, if the file is not there,
from `~/.config/vauxhall/`. Environment variables override file values, which
override the defaults. Hooks use only the `mqtt` and `logging` sections. See
`vauxhall_dashboard.json.example` and `vauxhall_hooks.json.example`.

| Section | Field | Environment variable | Default | Valid values |
| --- | --- | --- | --- | --- |
| `mqtt` | `host` | `VAUXHALL_MQTT_HOST` | `localhost` | Non-empty string |
| `mqtt` | `port` | `VAUXHALL_MQTT_PORT` | `1883` | Integer 1–65535 |
| `mqtt` | `keepalive` | `VAUXHALL_MQTT_KEEPALIVE` | `60` | Integer 0–65535 |
| `logging` | `level` | `VAUXHALL_LOGGING_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `dashboard` | `port` | `VAUXHALL_DASHBOARD_PORT` | `8080` | Integer 1–65535 |
| `dashboard` | `debug` | `VAUXHALL_DASHBOARD_DEBUG` | `false` | Boolean (`true`/`false`, `1`/`0`, or `yes`/`no`) |
| `dashboard` | `window_title` | `VAUXHALL_DASHBOARD_WINDOW_TITLE` | `Vauxhall Agent Dashboard` | Non-empty string |
| `dashboard` | `width` | `VAUXHALL_DASHBOARD_WIDTH` | `1000` | Integer 320–16384 |
| `dashboard` | `height` | `VAUXHALL_DASHBOARD_HEIGHT` | `800` | Integer 320–16384 |
| `dashboard` | `stale_threshold` | `VAUXHALL_DASHBOARD_STALE_THRESHOLD` | `120` | Integer 1–86400 seconds |
| `dashboard` | `pending_update_limit` | `VAUXHALL_DASHBOARD_PENDING_UPDATE_LIMIT` | `500` | Integer 1–10000 |
| `dashboard` | `max_active_agents` | `VAUXHALL_DASHBOARD_MAX_ACTIVE_AGENTS` | `100` | Integer 1–1000 |
| `dashboard` | `max_payload_bytes` | `VAUXHALL_DASHBOARD_MAX_PAYLOAD_BYTES` | `65536` | Integer 1024–1048576 bytes |

Invalid values (malformed JSON, non-object sections, wrong types, out-of-range
values, or unparsable environment values) stop the dashboard at startup. The
error names the environment variable or file path, the field, the value, and
the expected constraint. Hooks print the error to stderr and still return valid
protocol JSON. MQTT authentication and TLS are not supported yet (issue #3).

`vauxhall.core.config_store` saves configuration for the planned settings
editor (issue #29):

- `save_user_config(filename, config_type, changes)` always writes the per-user
  file `~/.config/vauxhall/<filename>`. It merges the changes into the existing
  file, keeps other keys, removes values equal to their defaults, validates the
  result with the same loader the dashboard or hooks use, and replaces the file
  atomically.
- `field_sources(filename, config_type)` reports whether each field comes from
  an environment variable, a file, or its default, and whether saving can
  change it.

A field can't be saved when an environment variable sets it, or when a
configuration file exists in the current directory, because that file hides the
per-user file entirely. Unknown or read-only fields, malformed files, and
invalid values raise `ConfigurationError` and leave the file unchanged.

### Settings dialog

The ⚙️ toolbar button opens a dialog with one row per field. Each row shows
where the value comes from (default, file, or environment) and has a reset
button. Fields set by an environment variable, and every field when a
configuration file exists in the current directory, are read-only. Values are
checked as you type and again when saving; if anything is invalid, nothing is
saved.

Saved changes take effect as follows:

| When | Fields |
| --- | --- |
| Immediately | `logging.level`, `dashboard.stale_threshold`, `dashboard.max_active_agents`, `dashboard.max_payload_bytes` |
| After reconnecting to the broker | `mqtt.host`, `mqtt.port`, `mqtt.keepalive` |
| After restarting Vauxhall | `dashboard.port`, `dashboard.debug`, `dashboard.window_title`, `dashboard.width`, `dashboard.height`, `dashboard.pending_update_limit` |

Lowering `max_active_agents` removes the least recently seen surplus cards
right away. When the MQTT
values in the dialog differ from the ones the hooks use, including after a
reset, **Also update hooks configuration** saves the differing values to
`~/.config/vauxhall/vauxhall_hooks.json`, even if the dashboard's own values
are unchanged. Both files are validated
before either is written. This doesn't affect hooks that get `VAUXHALL_MQTT_*`
environment variables, run in a workspace with its own `vauxhall_hooks.json`, or
run on another machine. The option is unavailable, with the reason shown, when
the hooks configuration is malformed or a `vauxhall_hooks.json` in the current
directory takes precedence over the per-user file.

### Remembered view

The dashboard keeps view preferences in `~/.config/vauxhall/dashboard_state.json`,
separate from the configuration files. It writes this file itself; you don't
need to edit it.

- **Theme, sort order, and history state filter** are saved half a second after
  you change them, or right away when the dashboard closes. A change you make
  before the saved preferences load is kept. The search text is not saved.
- **Window size, position, and maximized state** are saved when the dashboard
  closes. A saved size replaces `dashboard.width` and `dashboard.height`, which
  only set the size on first start. A saved position is used only if the
  window's top edge would still be on a connected screen. A maximized window
  keeps the normal size and position it had when the dashboard started, so if
  you move it to another monitor before maximizing, it reopens on the first one.
- **Theme on first paint**: the theme is also kept in the page's local storage,
  so the dashboard starts with the right theme before the state file is read.
  A theme saved there by earlier versions is copied to the state file the first
  time the dashboard starts.

Unknown keys and invalid values are ignored. An unreadable or corrupt file is
logged and treated as empty.

## Telemetry

Producers publish schema version 1 JSON to
`vauxhall/agents/<agent_name>/activity`. The `schema_version`, `agent`,
`workspace`, `session_id`, and `state` fields are required. `session_id` must
stay the same for a whole session and be unique among concurrent sessions of
the same agent in the same workspace; generate a UUID when the session starts.

```python
from uuid import uuid4

from vauxhall.hooks.client import TelemetryClient

session_id = str(uuid4())
client = TelemetryClient(host="localhost", port=1883)
client.send(
    agent="MyAgent",
    workspace="/path/to/project",
    session_id=session_id,
    state="Acting",
    tool="grep",
)
```

The dashboard logs and drops oversized, malformed, and invalid messages. See
[AGENTS.md](AGENTS.md#telemetry-schema) for the full schema and field limits.

## Project Structure

- `vauxhall/core/`: Configuration, logging, and telemetry validation shared by
  the dashboard and hooks.
- `vauxhall/dashboard/`: The Pyloid dashboard and its JavaScript UI.
- `vauxhall/hooks/`: The telemetry client, shared hook helpers, and the Claude
  Code, Codex, and Gemini CLI hooks and installers.
- `scripts/`: The agent simulator and a logging color check.
- `tests/`: Python tests mirroring the `vauxhall/` package layout, with frontend tests in `tests/dashboard/ui/`.

## Development

Follow the [development rules](AGENTS.md#development-and-maintenance-rules):

- **Setup**: Install [uv](https://docs.astral.sh/uv/) and run
  `uv sync --locked`. It creates `.venv` with the exact versions in `uv.lock`,
  the same environment CI uses. After changing dependencies in
  `pyproject.toml`, run `uv lock` and commit `uv.lock`.
- **Python**: Run `ruff format .` and `ruff check .` with the pinned Ruff
  version, then `.venv/bin/pytest`. The packaged dashboard startup test is
  deselected by default because it downloads Qt; run it with
  `.venv/bin/pytest -m packaged`.
- **Frontend**: With Node.js 20.19 or newer, run `npm ci` once, then
  `npm test`.
- **Coverage**: `.venv/bin/pytest --cov` and, on Node.js 22.8 or newer,
  `npm run test:coverage` check the floors CI enforces. Raise a floor when
  coverage rises rather than lowering it to make a change pass.
- **Packaging**: After changing metadata, entry points, or bundled assets, run
  `python -m build` and `twine check dist/*`.

## License

MIT
