<p align="center">
  <a href="https://github.com/ipapadop/vauxhall">
    <img src="vauxhall/dashboard/ui/logo.svg" width="150" alt="Vauxhall Logo">
  </a>
</p>

# Vauxhall Agent Dashboard

Vauxhall is a real-time dashboard for AI coding agents such as Claude Code,
Codex, and Gemini CLI. Agents publish telemetry over MQTT, and the dashboard
shows each agent session as a card in a grid.

## Features

- **Live state**: Cards are color-coded by state: Acting, Thinking, Waiting for
  Input, Input Required, Error, or Idle.
- **Session-aware cards**: Cards are keyed by agent, workspace, and session ID,
  so concurrent sessions in one workspace stay separate. Up to 100 cards are
  kept by default; a new session evicts the least recently seen card.
- **Activity log**: Each card shows its last 5 events with `[HH:mm:ss]`
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
- **Claude Code, Codex, and Gemini CLI hooks**: Installers register hooks that
  report prompts,
  tool activity, permission waits, tool outcomes (completed, failed, cancelled,
  or result unavailable), and idle state. Tool results are never published.
- **Safe handling**: Telemetry is validated and size-limited, rendered as text,
  and never turned into shell commands. Hooks always return valid protocol JSON,
  even when telemetry fails.

## Architecture

1. **Hooks (producers)**: Python modules run by agent hook events publish
   telemetry to an MQTT broker.
2. **Mosquitto (broker)**: Routes telemetry from hooks to the dashboard.
3. **Dashboard (consumer)**: A Pyloid desktop app with a Python MQTT backend and
   a vanilla JavaScript frontend.

## Requirements

- Python 3.10 or newer
- Mosquitto MQTT broker (for example, `brew install mosquitto` or
  `sudo apt install mosquitto`)

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

Run the installer from the agent's workspace:

```bash
# Claude Code
vauxhall-install-claude

# Codex
vauxhall-install-codex

# Gemini CLI
vauxhall-install-gemini
```

Each installer recreates `.vauxhall-venv` in the workspace and installs
Vauxhall into it from the same source as the running copy: the same Git
commit, local directory, or wheel file, or otherwise the matching PyPI
release. It then registers hooks that run the installed hook module, so the
hooks don't run code from a source checkout. Before changing an
existing hook or settings file, the installer backs it up and validates it. If
the file is invalid, the installer leaves it unchanged and exits with an error.
Reinstalling replaces only Vauxhall's own handlers and writes the file
atomically, preserving unrelated settings and hooks. The Claude Code installer
writes `.claude/settings.local.json`; restart Claude Code or open `/hooks` to
apply the hooks. For Codex, open `/hooks` after installing to review and trust
the new project hooks.

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
  version, then `.venv/bin/pytest`.
- **Frontend**: With Node.js 20.19 or newer, run `npm ci` once, then
  `npm test`.
- **Packaging**: After changing metadata, entry points, or bundled assets, run
  `python -m build` and `twine check dist/*`.

## License

MIT
