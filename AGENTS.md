# Vauxhall Development Guide

This file is for contributors and coding agents working on Vauxhall: the
architecture, the dashboard's behavior and implementation, and the rules for
developing and releasing it. User documentation lives in [README.md](README.md)
and [docs/](docs/): [integrations](docs/integrations.md) (telemetry schema,
states, and each agent's hooks), [sending prompts](docs/sending-prompts.md),
[configuration](docs/configuration.md),
[privacy](docs/privacy.md), [remote deployment](docs/remote-deployment.md),
[troubleshooting](docs/troubleshooting.md), and
[versioning](docs/releasing.md).

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

A fourth piece runs the other way: `vauxhall-relay`, a long-lived process on
each agent machine, receives prompts the dashboard publishes and types them
into the session's tmux pane (see [Prompt Delivery](#prompt-delivery)).

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

## Prompt Delivery

```mermaid
sequenceDiagram
    participant U as Dashboard UI
    participant D as DashboardApp
    participant B as Mosquitto
    participant R as vauxhall-relay
    participant T as tmux pane

    Note over R,T: SessionStart hook recorded session to pane
    U->>D: send_prompt(agent, session_id, text)
    D->>B: prompt (QoS 1, not retained)
    B->>R: sessions/{session}/prompt
    R->>T: paste-buffer -p, then Enter
    R->>B: ack (delivered or failed)
    B->>D: sessions/{session}/ack
    D->>U: prompt-ack event
```

See [sending-prompts.md](docs/sending-prompts.md) for the user's view.

- **Protocol**: `vauxhall.core.prompts` builds the per-session topics
  (`vauxhall/agents/<agent>/sessions/<session>/prompt` and `/ack`; agent
  lower-cased, session percent-encoded) and encodes, validates, and parses
  both messages. Prompt text is 1..4,096 characters with no control
  characters except newline and tab, because a raw escape could end the
  terminal's bracketed paste early and turn the rest into keystrokes. Both the
  dashboard and the relay validate it. Messages over 16 KiB are dropped.
- **Pane record**: `vauxhall.hooks.panes` writes
  `~/.config/vauxhall/panes/<sha256(agent, session)>.json` (mode 0600 in a
  0700 directory) holding `pane`, `socket`, and `server_pid`. It is written
  by `common.track_pane`, called from `publish_telemetry` on `SessionStart`
  and deleted on `SessionEnd`; a `SessionStart` outside tmux removes any old
  record, records older than 30 days are swept, and failures are logged and
  ignored. It is never published.
- **Relay**: `vauxhall.hooks.relay` (`vauxhall-relay`) subscribes at QoS 1 to
  `vauxhall/agents/+/sessions/+/prompt` with the hooks' broker settings. It
  ignores prompts for sessions without a local pane record, so one relay per
  machine can share a broker, and remembers the last 256 message IDs to
  ignore a QoS 1 redelivery. Delivery checks that the pane's tmux server PID
  still matches the record (pane IDs restart from `%0` after tmux restarts),
  then runs `load-buffer` from standard input, `paste-buffer -p -d` into the
  pane, and, after 0.2 seconds, `send-keys Enter`. Text never appears on a
  command line. It acknowledges `delivered` or `failed` (`pane-unavailable`
  or `delivery-failed`) without waiting for the broker, since it runs in the
  network loop's callback. It logs no prompt text.
- **Dashboard**: `DashboardSubscriber.send_prompt` publishes at QoS 1 with
  `retain=False` (a retained prompt would be retyped on every relay
  reconnect) and refuses when the broker isn't connected rather than queueing.
  It also subscribes to `vauxhall/agents/+/sessions/+/ack` and forwards valid
  acknowledgments to `DashboardApp.on_ack`, which sends a `prompt-ack` event
  to a ready frontend. `DashboardIPC.send_prompt` takes a JSON object with
  `agent`, `session_id`, and `text` and returns `{"ok", "id"}` or
  `{"ok": false, "error"}`.
- **Frontend**: A card's ✉️ button (`.prompt-icon`, named by agent, workspace,
  and session) opens the `prompt-modal` `<dialog>` through `dialog.js`, with a
  warning when the card is waiting for input, since the text would answer its
  question or permission request. `js/prompt.js` sends the request and shows
  the state in the card's `.prompt-status` live region: waiting for the relay,
  delivered, not delivered with a reason, or, after 10 seconds, no
  acknowledgment. An acknowledgment that beats the bridge's reply is kept
  briefly and matched afterwards. The dialog closes when its card is evicted,
  cleared, or denylisted.
- **Security**: Without MQTT authentication and ACLs (issue #3), anyone who
  can publish to the broker can send prompts, and a prompt can make an agent
  run commands. There is no setting that disables the feature; without a
  relay nothing acts on prompts.

## Project Structure

- `vauxhall/core/`: Configuration, logging, and telemetry validation shared by
  the dashboard and hooks.
- `vauxhall/dashboard/`: The Pyloid dashboard and its JavaScript UI.
- `vauxhall/hooks/`: The telemetry client, shared hook helpers, the tmux pane
  record and the prompt relay, and the Claude Code, Codex, and Gemini CLI
  hooks and installers.
- `docs/`: User documentation and the dashboard screenshot shown in the README.
- `scripts/`: The agent simulator and a logging color check.
- `scripts/release_notes.py`: The release workflow's tag and changelog check.
- `tests/`: Python tests mirroring the `vauxhall/` package layout, with
  frontend tests in `tests/dashboard/ui/`.

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
- **Fleet summary**: A live region under the header shows the total card
  count, how many need attention (`Error` or a waiting state), how many are
  stale, and the summed tokens across every card's last operation. It shows
  zero totals on load and re-renders after every telemetry update, staleness
  sweep, settings change, and **Clear**/**Clear Stale**.
- **Attention first**: A toolbar checkbox ranks cards needing attention
  (`Error` or a waiting state) before the rest, on top of whatever sort is
  chosen; it re-sorts on every telemetry update while checked.
- **Notifications**: A toolbar checkbox, unchecked by default, shows an OS
  notification (through `Pyloid.show_notification`) each time a card moves
  into `Error` or a waiting state from one that wasn't; it does not repeat
  while a card stays in an attention state.
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
- **Agent menu**: A card's ⋮ button opens a `<dialog>` with two actions.
  **Hide until next event** sets `display: none` on that card (tracked
  through `dataset.hidden`, not removed from `agents` state or the DOM); the
  card reappears, unhidden, the next time its identity's telemetry arrives. A
  hidden card stays hidden through search filtering. **Add agent to
  denylist** reads the current `dashboard.agent_denylist` from
  `DashboardIPC.get_settings()`, appends the agent's name (not its workspace
  or session), and saves it through `DashboardIPC.save_settings()` like any
  other setting; a `get_settings()` error or a read-only `agent_denylist`
  (its `agent_denylist_editable`) is logged and the save is skipped.
- **Settings**: The ⚙️ button opens a `<dialog>` built from
  `DashboardIPC.get_settings()`, with a source badge, reset button, and inline
  error per field. Read-only fields are disabled with the reason shown. Escape
  or Cancel closes it and focus returns to the button. The hooks option
  appears when an editable MQTT value differs from `hooks_mqtt`, the values
  the hooks use. Save sends only changed values to
  `DashboardIPC.save_settings()`, with `update_hooks` set when the option is
  checked; server errors appear next to the
  named field, and the dialog stays open to show restart or hooks notes. Below
  the fields, a denylisted-agents list (from `get_settings()`'s
  `agent_denylist`) offers a **Remove** button per entry, hidden when the list
  is empty; removing an entry saves it alongside any other unsaved field
  edits in the same request, and when `agent_denylist_editable` is false the
  buttons are disabled with a note, matching a read-only field. See
  [configuration.md](docs/configuration.md#settings-dialog) for when each
  field takes effect.
- **Accessibility**: Every interactive control is a `<button>` or a labeled
  form control; no `div` or `span` carries a click handler as its only way in.
  The card's workspace path, its 🕒 history icon, and its ⋮ menu icon are
  buttons, and the card's own click-to-copy handler sits on top of the
  workspace button rather than replacing it. The history, agent menu, prompt, and
  settings modals are `<dialog>` elements opened with `showModal()`, so the
  browser contains focus and Escape closes them; closing returns focus to the
  control that opened it, or to the agent grid when that control's card was
  evicted meanwhile. Each card is a `group` named by agent and session, and its
  history and menu buttons name the agent, workspace, and session, so
  concurrent sessions stay distinguishable. Search, sort, filter, and
  theme controls carry `aria-label`s, the status line is `role="status"` with
  `aria-live="polite"`, and `:focus-visible` draws an accent outline. Under
  `prefers-reduced-motion: reduce`, `--transition-speed` drops to `0.01ms` and
  `sortGrid` re-orders without animating.
- **Remembered view**: The first paint uses the theme cached in the
  `vauxhall-theme` localStorage key. On startup the frontend then applies the
  theme, sort order, history state filter, and the attention-first and notify
  checkboxes from `DashboardIPC.get_ui_state()` without delaying IPC setup,
  skipping any preference the user already changed, and re-sorts existing
  cards. If no theme is saved, the cached theme (from earlier versions) is
  saved. Changes are batched and sent to `DashboardIPC.save_ui_state()` 500 ms
  after the last one, or immediately on `pagehide`; a `false` result is
  logged. Theme changes also update the localStorage cache.
- **Remembered cards**: After `max_active_agents` and the real
  `stale_threshold` load, and before live telemetry starts, the frontend
  restores card shells from `DashboardIPC.get_saved_cards()`: agent,
  workspace, session ID, last known state, env, and last-seen time, with no
  prompt, message, command, error, token, or history content. A card for a
  currently denylisted agent is left out, like live telemetry. Restored
  cards are sorted by last-seen and capped to `max_active_agents` before any
  are built, are given an empty history (so the 🕒 button opens showing no
  events instead of silently doing nothing), and are checked for staleness
  immediately against the real threshold. A matching live event updates a
  restored card in place instead of creating a duplicate. Card state is sent
  to `DashboardIPC.save_cards()` 500 ms after a card is added, updated, or
  removed, or immediately on `pagehide`; **Clear** and **Clear Stale** also
  trigger a save so removed cards don't reappear on the next start.

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
  ready, it receives a `settings-changed` event with the new stale threshold,
  card limit, and agent denylist; the frontend removes any card whose agent is
  newly denylisted. `vauxhall.hooks.config` is imported lazily, so a malformed
  hooks file only disables the hooks option. `on_telemetry` drops an event
  whose `agent` is in `dashboard.agent_denylist` before it is queued or
  dispatched, so a denylisted agent's telemetry never reaches the frontend;
  it rechecks the denylist immediately before dispatch, under the same lock
  `_apply_settings` dispatches `settings-changed` through, so a denylist save
  racing a card's telemetry cannot resurrect a card that save just removed.
  `agent_denylist` is a list-valued field; unlike every other setting it isn't
  settable by an environment variable, and it is described separately from
  `DashboardIPC.get_settings()`'s per-field `fields` list (as `agent_denylist`
  and `agent_denylist_editable`) so the settings editor doesn't try to render
  it as a scalar input.
- **View state**: `vauxhall.dashboard.ui_state` reads and writes
  `~/.config/vauxhall/dashboard_state.json`. It keeps only known keys with
  valid values, treats an unreadable file as empty, and writes atomically.
  Each update holds one lock across load, merge, and write, so a frontend save
  and the shutdown window save can't discard each other's fields.
  `save_ui_state` accepts only `theme`, `sort`, `history_filter`,
  `attention_first`, and `notify`, the last two as booleans; only Python
  writes `window`. `run()` creates the window with the saved size, calls
  `set_position` only when `visible_position` finds the top edge on a monitor's
  available area, and maximizes after showing the window. When the UI loop
  exits, it saves the size and position from Pyloid's public `get_size`,
  `get_position`, and `is_maximized`. A maximized window keeps its previous
  normal size, and a save failure is logged without blocking shutdown.
- **Card state**: `vauxhall.dashboard.card_state` reads and writes
  `~/.config/vauxhall/dashboard_cards.json` as `{"cards": [...]}`. Each entry
  keeps only `agent`, `workspace`, `session_id`, `state` (one of
  `vauxhall.core.telemetry.SUPPORTED_STATES`), `env`, and `last_seen`; an
  invalid entry is dropped rather than rejecting the whole file, entries are
  deduplicated by identity keeping the newest `last_seen`, and the list is
  capped to a defensive maximum. `save_cards` replaces the file atomically
  with the frontend's full current snapshot; there is no merge, so no lock is
  needed beyond the atomic write itself. `DashboardIPC.get_saved_cards()`
  leaves out any card whose agent is in the current `agent_denylist`, the
  same as live telemetry.
- **Shutdown**: When the UI loop exits, including after an exception or partial
  startup failure, the dashboard marks the frontend not ready and stops the
  MQTT client once. The final `Disconnected` status and any late telemetry are
  kept instead of being sent to the destroyed window.
- **Dialogs**: `vauxhall/dashboard/ui/js/dialog.js` opens and closes both
  modals. `openDialog` prefers `showModal()` and does nothing on an open
  dialog; `closeDialog` prefers `close()`. Without native dialog support both
  fall back to the `open` attribute, and the fallback dispatches the `close`
  event itself, so focus restoration and view state run on one path.
- **Window icon**: `DashboardApp._create_window` calls `Pyloid.set_icon` with
  `vauxhall/dashboard/ui/icon.png` before creating the window, because Pyloid
  reads `app.icon` while the window loads and otherwise logs `Icon is not set.`
  The packaged startup test fails if that line appears.
- **Pyloid**: Pyloid 0.27.2 or newer is required. Its `BrowserWindow` marshals
  cross-thread commands to the UI thread, so MQTT callbacks call
  `window.invoke()` directly. Vauxhall does not use Pyloid's private symbols.
- **Notifications**: `DashboardIPC.notify` calls the `on_notify` callback
  `DashboardApp` registers, which calls `Pyloid.show_notification` for an
  OS-level (system tray) notification. Without a registered callback, or if
  it raises, `notify` returns `False` instead of propagating.

## Configuration

The dashboard reads `vauxhall_dashboard.json` and hooks read
`vauxhall_hooks.json`, from the current directory or, if the file is not there,
from `~/.config/vauxhall/`. Environment variables override file values, which
override defaults. See [configuration.md](docs/configuration.md) for every
field and environment variable.

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
[configuration.md](docs/configuration.md) for details.

## Development and Maintenance Rules

**Setup**: Install [uv](https://docs.astral.sh/uv/) and run `uv sync --locked`.
It creates `.venv` with the exact versions in `uv.lock`, the same environment
CI uses. After changing dependencies in `pyproject.toml`, run `uv lock` and
commit `uv.lock`. For the frontend, install Node.js 20.19 or newer and run
`npm ci` once.

All contributors, including AI agents, must:

1. **Code style**: Before committing Python changes, run `ruff format .` and
   `ruff check .` with the Ruff version pinned in `pyproject.toml`, and fix every
   error (`ruff check --fix .` fixes many). Every Python file must start with the
   project's SPDX copyright and license headers.
2. **Testing**: All tests must pass before committing.
   - Run `.venv/bin/pytest`. The packaging tests build real wheels, check
     metadata and bundled UI assets, install the wheel into clean environments,
     run the hook installers outside the source checkout, and check that the
     sdist contains every tracked file except `.github/` and `.gitignore`.
     A new top-level file that the tests or build need goes in `MANIFEST.in`.
     After changing metadata, entry points, or bundled assets, also run
     `python -m build` and `twine check dist/*` to reproduce that check locally.
   - `.venv/bin/pytest -m packaged` runs the packaged dashboard startup test,
     which is deselected by default because it downloads Qt. CI runs it on
     Linux, macOS, and Windows.
   - With Node.js 20.19 or newer, run `npm test` for the frontend.
   - Add unit tests for every new feature and bug fix.
3. **Coverage**: Both suites have a floor that CI enforces, so a change that
   leaves new code untested fails.
   - `.venv/bin/pytest --cov` checks the Python floor in
     `[tool.coverage.report]`.
   - `npm run test:coverage` checks the frontend floor over
     `vauxhall/dashboard/ui/js`. It needs Node.js 22.8 or newer for the
     coverage thresholds; plain `npm test` runs on 20.19.
   - Raise a floor when coverage rises. Never lower one to make a change pass;
     write the missing test instead.
4. **Documentation**: After every change, update the documents it affects so
   they match the code: `README.md` (features, first run),
   `docs/integrations.md` (schema, states, hooks), `docs/configuration.md`,
   `docs/privacy.md` (anything that changes what is published or stored), and
   `AGENTS.md` (architecture, dashboard behavior, and internals). Add a line
   for every user-visible change under `## [Unreleased]` in `CHANGELOG.md`; see
   [docs/releasing.md](docs/releasing.md) for the versioning policy and
   [Releasing](#releasing) below for the release process.
5. **Accessibility**: Dashboard changes must keep the contract under
   [Dashboard Behavior](#dashboard-behavior). Reviews reject a change that
   breaks any of these, so check them before opening one:
   - Anything a user activates is a `<button>` or a native form control. Never
     give a `div` or `span` a click handler and call it done.
   - Every control has an accessible name: its own text, a `<label for>`, or an
     `aria-label`. A `title` alone is not a name.
   - A new overlay is a `<dialog>` opened with `showModal()` through
     `vauxhall/dashboard/ui/js/dialog.js`, and focus returns to whatever opened
     it. Do not hand-roll a focus trap or toggle `style.display`.
   - Text that changes on its own belongs in a live region.
   - New motion is timed by `--transition-speed` or is skipped when
     `prefers-reduced-motion: reduce` matches. Do not hard-code a duration.
   - Cover the keyboard and dialog behavior of anything new in
     `tests/dashboard/ui/accessibility.test.js`.
6. **Assets**: `vauxhall/dashboard/ui/icon.png` is a 256x256 render of
   `vauxhall/dashboard/ui/logo.svg` centered on a rounded dark tile, and
   `docs/dashboard.png` is a capture of the running dashboard. Refresh the
   screenshot whenever the dashboard changes visibly, from a real run with
   representative telemetry, not a mock-up.
7. **History**: The commit history is a record, not a scratch space. Do not
   squash or rewrite it as cleanup. Every file must carry the maintainer's
   GitHub no-reply address, the same one the package metadata and the commit
   metadata use.

## Releasing

See [docs/releasing.md](docs/releasing.md) for the versioning policy this
process implements.

### Changelog

[CHANGELOG.md](CHANGELOG.md) follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Every pull request
with a user-visible change adds a line under `## [Unreleased]`, in the
**Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, or
**Security** group. Links in an entry must be absolute URLs, such as
`https://github.com/ipapadop/vauxhall/blob/main/docs/privacy.md`, because the
entry becomes the GitHub release notes, where relative links don't resolve.

### Making a release

1. On a branch, set `version` in `pyproject.toml`, run `uv lock`, and rename
   `## [Unreleased]` in the changelog to `## [<version>] - <YYYY-MM-DD>`. Add
   a new, empty `## [Unreleased]` above it. In the entry, record the Claude
   Code, Codex, and Gemini CLI versions you checked the hooks with, following
   the [first run](README.md#first-run) with each. Merge the pull request.
2. Tag the merge commit on `main` and push the tag:

   ```bash
   git switch main && git pull
   git tag -a v0.1.0 -m "Vauxhall 0.1.0"
   git push origin v0.1.0
   ```

3. The [release workflow](.github/workflows/release.yml) then:
   1. runs the lint workflow and the whole CI workflow: Ruff, the Python
      suite on every supported Python and operating system, the coverage
      floors, the frontend suite, both test suites from the unpacked sdist,
      and the packaged dashboard on Linux, macOS, and Windows;
   2. checks that the tagged commit is on `main`, that the tag is `v` followed
      by the package version, and that the changelog has a dated, non-empty
      entry for it (`scripts/release_notes.py`);
   3. builds the sdist, and the wheel from that sdist, each in an isolated
      build environment, with timestamps taken from the tagged commit;
   4. runs `twine check --strict`, installs the wheel into a clean
      environment, and runs `vauxhall-hook-install --help` from it;
   5. creates a draft GitHub release with the wheel, the sdist, and a
      `SHA256SUMS` file, using the changelog entry as its notes, and then
      publishes it.

   If any step fails, nothing is published. A transient failure can be
   re-run from the Actions page; the last job reuses a draft release that an
   earlier attempt left behind. To change what is released instead, delete
   that draft if there is one (`gh release delete v0.1.0`), delete the tag
   (`git push --delete origin v0.1.0`; with the tag ruleset below, only an
   admin can), fix the problem, and tag again.

To check a download, run `sha256sum -c SHA256SUMS` in the directory that holds
the release files.

### Repository settings

Two settings protect published releases. They are configured on GitHub, not
in the repository:

- **Immutable releases** (*Settings → General → Releases*). Once a release is
  published, its files and tag can't be changed. The workflow attaches every
  file before publishing for this reason.
- **A tag ruleset** that blocks moving or deleting `v*` tags. Rulesets need
  a public repository or GitHub Pro (see issue #17). Once available, create it
  with:

  ```bash
  gh api repos/ipapadop/vauxhall/rulesets --method POST --input - <<'EOF'
  {
    "name": "Release tags",
    "target": "tag",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "rules": [{"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}],
    "bypass_actors": [
      {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    ]
  }
  EOF
  ```

  Role `5` is the repository admin role. The rules block updating and
  deleting release tags for everyone else. Creating a tag isn't restricted:
  only people with write access can push tags at all.

### Not done yet: PyPI

Releases go to GitHub only. Publishing to PyPI is planned as a separate job
in the same workflow. It will use Trusted Publishing (OIDC) instead of an API
token, run in a protected `pypi` environment that needs a maintainer's
approval, and be rehearsed on TestPyPI before the first production upload.
Until then, install from a GitHub release or tag, as shown in the
[README](README.md#installation).
