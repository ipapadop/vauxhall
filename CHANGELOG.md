<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Changelog

All notable changes to Vauxhall are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
the [versioning policy](docs/releasing.md#versioning-policy).

## [Unreleased]

The first release, planned as 0.1.0. It is alpha software; see
[known limitations](https://github.com/ipapadop/vauxhall#known-limitations).

### Added

- Desktop dashboard (`vauxhall`) that shows each agent session as a card, with
  live state, an activity log, search, sort, stale detection, and a settings
  dialog. Clicking a card grows it into an activity pane with a timeline of
  its last 20 events: a bar per event, colored by state and as long as the
  time spent in it, with any duration the tool reported, and a **Copy path**
  button for the workspace. A fleet summary bar totals cards, cards needing
  attention, stale cards, and tokens; an **Attention first** toggle ranks
  cards needing attention above the chosen sort; and an opt-in **Notify me**
  toggle shows a desktop notification when a card starts needing attention.
  It remembers its theme, sort order, history filter, these two toggles, and
  window geometry, and restores each card's identity and last known state
  across restarts, never prompt, message, command, error, token, or history
  content.
- A per-card menu to hide a card until its agent's next event, or add the
  agent to a denylist saved in the dashboard configuration; denylisted
  agents' telemetry is dropped and their cards removed, until the denylist
  entry is removed from the settings dialog.
- MQTT user name and password authentication, and TLS with certificate
  verification and optional client certificates, for the dashboard and the
  hooks. The password comes from `VAUXHALL_MQTT_PASSWORD` or a
  `password_file`, never a configuration file. See
  https://github.com/ipapadop/vauxhall/blob/main/docs/remote-deployment.md#networked-brokers
  for a Mosquitto setup with an ACL.
- Hooks for Claude Code, Codex, and Gemini CLI, installed with
  `vauxhall-hook-install claude codex gemini` into an isolated `.vauxhall-venv`.
- Claude Code cards report tool calls denied by auto mode, show an MCP
  server's request for input at once and clear it when answered, and show
  when a usage-limit pause resumes, needs **Enter**, or ends. Reinstall the
  Claude Code hooks to register the new events.
- An **Install Hooks…** dashboard button that picks a local workspace,
  detects which agents it uses and which already have Vauxhall hooks, and
  installs or reinstalls the chosen agents' hooks with a live installer log.
- A Python client, `vauxhall.hooks.client.publish`, and telemetry schema
  version 1 for other agents.
- JSON configuration files with environment variable overrides, validated at
  startup.
- Keyboard and screen reader support for every dashboard control.
- Documentation for a first run, configuration, privacy and the data each
  integration publishes, remote monitoring over SSH, troubleshooting,
  uninstalling, and a comparison with similar tools.
- A complete source distribution that can run every Python and frontend test.
- A tag-triggered release workflow that tests, builds, checks, and attaches
  the wheel and source distribution to a GitHub release.
- A `dashboard.graphics_backend` setting (`auto`, `vulkan`, `opengl`, or
  `software`) that chooses how the window draws the page; see
  [configuration](https://github.com/ipapadop/vauxhall/blob/main/docs/configuration.md#graphics-backend).
- Support for Python 3.11 to 3.14 for the hooks, and 3.11 to 3.13 for the
  dashboard, which Pyloid doesn't yet support on 3.14.

### Fixed

- A session that changes directory keeps one card, which shows its latest
  workspace, instead of getting a new card for each directory. A Claude Code
  or Gemini CLI session ended by `/clear`, or a Claude Code session left by
  `/resume`, removes its card, since the agent continues under another
  session; its `SessionEnd` telemetry now carries the
  documented reason as `end_reason`. A producer's `session_id` must now be
  unique among an agent's concurrent sessions in every workspace, not only
  in one.
- Copying a workspace path works on Linux without `wl-clipboard`, `xclip`,
  or `xsel` installed. The dashboard now uses Qt's clipboard and no longer
  depends on pyperclip.
- A second dashboard for the same user exits with `Another Vauxhall Dashboard
  is already running` instead of running beside the first, where each would
  overwrite the other's saved view and cards.
- Telemetry with long non-ASCII details, such as a prompt of 4,096 emoji,
  is no longer dropped as oversized. Hooks escaped every non-ASCII
  character, which made such an event about three times larger than its
  UTF-8 text.
- When `vauxhall-hook-install` creates an agent's settings file, the `.bak`
  next to it now holds `{}`. Before, there was no backup on the first run,
  so the second run backed up the first run's output as if it were your
  original settings.
- Running `vauxhall-hook-install` after an install that was interrupted
  puts back the hooks environment that install set aside, if its own was
  left incomplete, and removes the copy otherwise. Before, a
  `.vauxhall-venv.old-…` directory stayed behind.
- The settings dialog shows "Settings could not be loaded; the dashboard
  log has details." for any failure, and the dashboard logs the error with
  its traceback. Before, a failure other than a configuration error was
  logged nowhere.
- Start times of tool calls that never finished, and files left by a
  killed hook, are now removed from the hooks' temporary directory after 24
  hours. Before, they stayed until the system cleared its temporary
  directory.
- A hook event whose working directory was deleted, or with an empty or
  missing `cwd`, is no longer dropped. Hooks used the hook process's own
  directory even when the event named one, and a blank `cwd` failed
  validation.
- Hook events that run at once no longer lose or repeat each other's work:
  concurrent Claude Code `MessageDisplay` or Gemini CLI `AfterModel` chunks
  could drop part of a message, and concurrent Codex hooks could publish the
  same interim message twice.
- A streamed Claude Code or Gemini CLI message chunk holding a lone
  surrogate, such as half of an emoji, is no longer left out of the
  published message. Its text couldn't be stored as UTF-8.
- A dashboard window closed narrower than 320 pixels, or wider than 16,384,
  now reopens where it was. Before, its width was not saved, and the window
  reopened at the default position and size. A window size outside these
  limits, in either direction, is now saved as the nearest limit.
- Saving settings, view state, or cards writes through a symlinked file in
  `~/.config/vauxhall` and keeps the link. Before, the link was replaced by
  a regular file, so a configuration kept in a dotfiles repository silently
  stopped updating.
- Running `vauxhall-hook-install` again keeps the existing `.bak` backup of
  the agent settings. Before, each run replaced it with the previous run's
  output, losing the original settings. A copy that fails partway no
  longer leaves a partial backup behind.
- Saving a broker change in the settings dialog no longer freezes the
  window for up to 5 seconds while the old connection is still trying to
  reach its broker. The old connection now closes in the background.
- Closing the dashboard while the broker is unreachable no longer keeps the
  process running for up to 5 seconds; it waits at most 1 second.
- **Hide until next event** moves keyboard focus to the card grid. Before,
  focus went back to the hidden card's ⋮ button, which can't take focus, so
  it was lost.
- A failed `vauxhall-hook-install`, for example when pip can't reach the
  package, no longer leaves `.vauxhall-venv` as an environment that lacks
  Vauxhall, which made every registered hook fail. The previous environment
  is kept until the new one is installed, a half-built one is removed, and
  pip's error is shown instead of a traceback without it.
- **Also update hooks configuration** no longer validates the hooks file
  with the dashboard's `VAUXHALL_*` environment variables, which the hooks
  may not have. A dashboard given `VAUXHALL_MQTT_TLS=true` could write
  `ca_certs` without `tls`, a file that hooks without that variable
  rejected. Those variables also no longer make hooks fields read-only.
- A prompt, command, or other text over 4,096 characters no longer stops
  hooks from publishing the event; it is cut off with an ellipsis, as
  assistant messages already were, so a long shell command, such as a
  heredoc that writes a file, now publishes its start. Gemini CLI's tool
  input (`args`) is left out instead, because it holds the complete input
  of every tool call. A session ID that would exceed 256 characters is
  replaced by its SHA-256 hash.
- A workspace path over 4,096 characters no longer stops hooks from
  publishing the event. It is shortened to its first 24 and last 48
  characters around an ellipsis, followed by `[sha256:<16 hex digits>]` of
  the full path, so workspaces that differ only in the middle keep separate
  cards; **Copy path** copies that shortened text, not a usable path.
- A TLS broker that accepts the connection but stalls the handshake no
  longer holds each hook for up to `mqtt.keepalive` seconds (60 by default).
  paho times the handshake with the keepalive, so hooks now connect with a
  1-second keepalive; their connections last about a second anyway.
- `mqtt.tls` with `mqtt.keepalive` set to 0 is now a configuration error.
  The TLS handshake could never finish, so the dashboard retried forever and
  hooks never connected.
- A Claude Code card shows `Idle` when a turn ends. Before, the final
  message's `Thinking` event often arrived after the turn's `Idle` event and
  left the card showing `Thinking` while the session waited for input
  ([#74](https://github.com/ipapadop/vauxhall/issues/74)).
- The Gemini CLI hook limits its MQTT connection attempt to 1 second, like the
  Claude Code and Codex hooks, instead of waiting longer when the broker is
  unreachable.
- The activity pane's **Waiting** filter shows `Input Required` events as
  well as `Waiting for Input` ones. Before, no state filter showed them.
- The dashboard passes the `QTWEBENGINE_CHROMIUM_FLAGS` you set on to its
  embedded browser. Before, importing Pyloid replaced them, so flags such as
  `--disable-gpu` had no effect; see
  [troubleshooting](https://github.com/ipapadop/vauxhall/blob/main/docs/troubleshooting.md#dashboard-startup).
- The dashboard window shows the page on Linux under Wayland. Before, Qt's
  OpenGL default could leave it blank; the dashboard now uses Vulkan on Linux
  when a Vulkan driver is available.
- The dashboard starts once when Pyloid signals readiness after the page
  loads. Before, it could start twice, registering every event listener and
  the readiness signal two times.
- The dashboard no longer freezes when telemetry arrives while settings are
  being saved, and no longer hangs when you change the broker or close the
  window while telemetry is arriving.
- A stale card shows its real state again when a raised stale threshold makes
  it fresh. Before, it kept showing `STALE` until its next event.
- Closing the dashboard before its remembered cards finish loading no longer
  saves an empty card list over them.
- A settings save that both denylists an agent and lowers the card limit
  removes the denylisted cards before evicting others. Before, it could evict
  cards that would have fit.

### Security

- Hook commands now run `python -P -m vauxhall.hooks.<agent>.telemetry_hook`.
  Agents run hooks in their workspace, and without `-P` Python searched it
  first, so a repository containing its own `vauxhall` package ran that
  code on every hook event. The installer's `venv` and `pip` steps use `-P`
  too. A reinstall doesn't recognize handlers written without `-P`, so remove
  them first, as described in
  https://github.com/ipapadop/vauxhall#uninstalling, then reinstall the hooks.
- Logs show control characters in messages, tracebacks, and stacks as
  `\xNN`. A terminal escape sequence in an MQTT topic, which the dashboard
  logs when it drops a message, could otherwise rewrite the terminal showing
  the log.
- A shell command over 4,096 characters, such as a heredoc that writes a
  file, is now published cut to its first 4,096 characters; before, the
  whole event was dropped. Short commands were always published in full.
  See [privacy](https://github.com/ipapadop/vauxhall/blob/main/docs/privacy.md).
- Hooks no longer read a `vauxhall_hooks.json` in the agent's workspace,
  only `~/.config/vauxhall/vauxhall_hooks.json`. A workspace file, for
  example one committed to a cloned repository, could point the hooks at any broker and send it your telemetry and broker
  password, or any file you can read as `password_file`. A hook that finds
  one ignores it and prints a warning; move its settings to the per-user
  file. The dashboard still reads `vauxhall_dashboard.json` from its current
  directory.
- The dashboard window checks HTTPS certificates. Pyloid turns those checks
  off for every page with `--ignore-certificate-errors` and
  `--allow-insecure-localhost`; the dashboard now removes both, since its UI
  is served over plain HTTP. Flags you set in `QTWEBENGINE_CHROMIUM_FLAGS` are
  kept as given.
- The dashboard no longer logs the workspace path it copies to the clipboard.
- Hooks keep tool start times in an owner-only directory, as
  [privacy](https://github.com/ipapadop/vauxhall/blob/main/docs/privacy.md#on-disk)
  describes. The directory was readable by other accounts, and one that
  another account created first, or a symlink, was used as found, so that
  account could read tool timing or plant start times that faked a tool's
  duration. A directory another account owns, or a symlink, is now refused
  with a warning, and the duration left out. One you own that others can
  reach, such as one an earlier version created, is made owner-only, and
  entries other accounts put in it are removed.
- The dashboard serves its UI itself and stops with an error when
  `dashboard.port` is taken. Before, it logged nothing useful and loaded
  whatever page another program served on that port, which, on a shared
  machine, could be another account's page with access to the dashboard's
  bridge.
- The dashboard's page sets a content security policy that allows only its
  own scripts, styles, and images, and no inline code.
- The dashboard opens only `http` and `https` links in the browser; before,
  any page script could ask it to open any URL, such as a `file:` one.
