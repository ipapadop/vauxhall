<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Configuration

Vauxhall needs no configuration when the broker runs on the same machine as
the dashboard and the agents. Everything below is optional.

## Files and precedence

| Component | File | Sections |
| --- | --- | --- |
| Dashboard | `vauxhall_dashboard.json` | `mqtt`, `logging`, `dashboard` |
| Hooks | `vauxhall_hooks.json` | `mqtt`, `logging` |

Each component looks for its file in two places and uses only the first one
it finds:

1. The current directory. For hooks this is the directory the agent runs them
   from, normally the workspace, so a workspace can point its hooks at a
   different broker.
2. `~/.config/vauxhall/` (on Windows, `%USERPROFILE%\.config\vauxhall\`).

The files are not merged: a file in the current directory hides the per-user
file entirely. For each field, an environment variable overrides the file,
which overrides the default. See `vauxhall_dashboard.json.example` and
`vauxhall_hooks.json.example` for complete files with every default.

## Fields

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
| `dashboard` | `agent_denylist` | Not settable via environment variable | `[]` | List of agent names |

Invalid values (malformed JSON, non-object sections, wrong types, out-of-range
values, or unparsable environment values) stop the dashboard at startup. The
error names the environment variable or file path, the field, the value, and
the expected constraint. Hooks print the error to stderr and still return valid
protocol JSON. MQTT authentication and TLS are not supported yet (issue #3);
see [remote-deployment.md](remote-deployment.md) for how to reach a remote
broker safely until then.

### Other environment variables

| Variable | Used by | Meaning |
| --- | --- | --- |
| `VAUXHALL_SESSION_ID` | Hooks | Session ID to use when the agent's hook event has neither a session ID nor a transcript path. Without any of the three, the hook skips the event. |

`dashboard.port` is the port of the dashboard's own UI server, which listens
only on `127.0.0.1`. It is unrelated to the MQTT port.

### Saving configuration from code

`vauxhall.core.config_store` saves configuration for the settings dialog and
for other tools:

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

## Settings dialog

The ⚙️ toolbar button opens a dialog with one row per field. Each row shows
where the value comes from (default, file, or environment) and has a reset
button. Fields set by an environment variable, and every field when a
configuration file exists in the current directory, are read-only. Values are
checked as you type and again when saving; if anything is invalid, nothing is
saved.

Saved changes take effect as follows:

| When | Fields |
| --- | --- |
| Immediately | `logging.level`, `dashboard.stale_threshold`, `dashboard.max_active_agents`, `dashboard.max_payload_bytes`, `dashboard.agent_denylist` |
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

### Denylisted agents

Each card's ⋮ menu has **Add agent to denylist**, which adds the agent's name
(not its workspace or session) to `dashboard.agent_denylist` and saves it
through the same settings pipeline. A denylisted agent's telemetry is dropped
before it reaches the dashboard, so no card for it is created; any of its
cards already on screen are removed immediately. The settings dialog lists
denylisted agents, each with a **Remove** button, below the regular fields.
Like any other field, the denylist is read-only, with the buttons disabled
and a reason shown, when a `vauxhall_dashboard.json` in the current directory
takes precedence over the per-user file.

## Remembered view

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

## Files Vauxhall writes

| Path | Written by | Contents |
| --- | --- | --- |
| `~/.config/vauxhall/vauxhall_dashboard.json` | Settings dialog | Changed dashboard settings |
| `~/.config/vauxhall/vauxhall_hooks.json` | Settings dialog, when **Also update hooks configuration** is checked | Changed hook MQTT settings |
| `~/.config/vauxhall/dashboard_state.json` | Dashboard | Theme, sort order, history filter, window geometry |
| `<workspace>/.vauxhall-venv/` | `vauxhall-hook-install` | The isolated environment the hooks run from |
| `.claude/settings.local.json`, `.codex/hooks.json`, `.gemini/settings.json` | `vauxhall-hook-install` | Hook registrations, with a `.bak` copy of the previous file |
| `vauxhall-*` directories in the system temporary directory | Hooks | Tool start times and partial assistant messages; see [privacy.md](privacy.md#on-disk) |

Telemetry itself is never written to disk by Vauxhall; see
[privacy.md](privacy.md).
