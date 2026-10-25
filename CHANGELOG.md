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
  live state, an activity log, a history modal, search, sort, stale detection,
  and a settings dialog. A fleet summary bar totals cards, cards needing
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
- Sending prompts from the dashboard to running Claude Code, Codex, and Gemini
  CLI sessions: a ✉️ button on each card publishes the prompt, and
  `vauxhall-relay`, run on the agent machine, types it into the session's
  tmux pane and reports delivery back to the card. The hooks record each
  session's tmux pane locally at `SessionStart`. Anyone who can publish to
  the broker can send prompts unless its ACL restricts them; see
  https://github.com/ipapadop/vauxhall/blob/main/docs/sending-prompts.md.
- MQTT user name and password authentication, and TLS with certificate
  verification and optional client certificates, for the dashboard, the hooks,
  and `vauxhall-relay`. The password comes from `VAUXHALL_MQTT_PASSWORD` or a
  `password_file`, never a configuration file. See
  https://github.com/ipapadop/vauxhall/blob/main/docs/remote-deployment.md#networked-brokers
  for a Mosquitto setup with an ACL that lets only the dashboard send prompts.
- Hooks for Claude Code, Codex, and Gemini CLI, installed with
  `vauxhall-hook-install claude codex gemini` into an isolated `.vauxhall-venv`.
- A Python client, `vauxhall.hooks.client.publish`, and telemetry schema
  version 1 for other agents.
- JSON configuration files with environment variable overrides, validated at
  startup.
- Keyboard and screen reader support for every dashboard control.
- Documentation for a first run, configuration, privacy and the data each
  integration publishes, remote monitoring over SSH, troubleshooting, and
  uninstalling.
- A complete source distribution that can run every Python and frontend test.
- A tag-triggered release workflow that tests, builds, checks, and attaches
  the wheel and source distribution to a GitHub release.
- A `dashboard.graphics_backend` setting (`auto`, `vulkan`, `opengl`, or
  `software`) that chooses how the window draws the page; see
  [configuration](https://github.com/ipapadop/vauxhall/blob/main/docs/configuration.md#graphics-backend).

### Fixed

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
- A prompt sent to a session whose tmux pane is in copy mode is now
  submitted whole. Copy mode took the relay's Enter for itself and dropped
  the paste's brackets, so a multi-line prompt's first line was submitted
  alone and the rest never was, while the dashboard reported it delivered.
  The relay now leaves the pane's mode first (tmux 3.1a or later).
- Prompt and acknowledgment messages with a `schema_version` other than the
  integer 1 (such as `true` or `1.0`), or a message ID that holds control
  characters, are now dropped like other invalid messages, as telemetry
  already was for its `schema_version`. Before, both were accepted.
- Saving a broker change in the settings dialog no longer freezes the
  window for up to 5 seconds while the old connection is still trying to
  reach its broker. The old connection now closes in the background.
- Closing the dashboard while the broker is unreachable no longer keeps the
  process running for up to 5 seconds; it waits at most 1 second.
- **Hide until next event** moves keyboard focus to the card grid. Before,
  focus went back to the hidden card's ⋮ button, which can't take focus, so
  it was lost.
- A card that shows `No relay acknowledged the prompt` now shows the
  outcome when the relay's acknowledgment arrives later, unless another
  prompt was sent from the card since. Before, an acknowledgment after the
  10-second wait was ignored, so a delivered prompt stayed reported as
  unacknowledged.
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
  cards; clicking the card copies that shortened text, not a usable path.
- A TLS broker that accepts the connection but stalls the handshake no
  longer holds each hook for up to `mqtt.keepalive` seconds (60 by default).
  paho times the handshake with the keepalive, so hooks now connect with a
  1-second keepalive; their connections last about a second anyway.
- `mqtt.tls` with `mqtt.keepalive` set to 0 is now a configuration error.
  The TLS handshake could never finish, so the dashboard and the relay
  retried forever and hooks never connected.
- The prompt relay no longer retypes a retained prompt each time it
  reconnects. A prompt another client publishes with the retain flag is
  typed only by a relay connected when it is published.
- The prompt relay keeps running after an unexpected error while handling a
  prompt, logs it, and acknowledges a delivery that raised as not delivered.
  Before, the error ended the relay, and later prompts went unanswered.
- Prompts and acknowledgments whose ID isn't valid text are dropped. Before,
  such a prompt passed validation and crashed the relay when delivered.
- A Claude Code card shows `Idle` when a turn ends. Before, the final
  message's `Thinking` event often arrived after the turn's `Idle` event and
  left the card showing `Thinking` while the session waited for input
  ([#74](https://github.com/ipapadop/vauxhall/issues/74)).
- The Gemini CLI hook limits its MQTT connection attempt to 1 second, like the
  Claude Code and Codex hooks, instead of waiting longer when the broker is
  unreachable.
- The history modal's **Waiting** filter shows `Input Required` events as
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
- A prompt send that finishes after you reopen the prompt dialog for another
  card no longer closes that dialog, clears its text, or shows the old send's
  error in it. A send rejected after its dialog closed or moved to another
  card now shows `Prompt not sent` and the reason on its own card, where
  before the reason was lost or shown in the wrong dialog.

### Security

- A shell command over 4,096 characters, such as a heredoc that writes a
  file, is now published cut to its first 4,096 characters; before, the
  whole event was dropped. Short commands were always published in full.
  See [privacy](https://github.com/ipapadop/vauxhall/blob/main/docs/privacy.md).
- Hooks and `vauxhall-relay` no longer read a `vauxhall_hooks.json` in the
  agent's workspace, only `~/.config/vauxhall/vauxhall_hooks.json`. A
  workspace file, for example one committed to a cloned repository, could
  point the hooks at any broker and send it your telemetry and broker
  password, or any file you can read as `password_file`. A hook that finds
  one ignores it and prints a warning; move its settings to the per-user
  file. The dashboard still reads `vauxhall_dashboard.json` from its current
  directory.
- The prompt relay no longer types a prompt into a shell. An agent that
  exited without ending its session, for example after a crash, left the
  shell in its tmux pane, and the relay pasted the prompt there, where it ran
  as a command. Hooks now record the pane's foreground command at session
  start, and the relay refuses delivery (`pane-unavailable`) when the pane
  runs something else. When the recorded command is unknown, as for
  sessions started before upgrading, or is a shell, as for an agent started
  by a wrapper script, the relay can't tell the agent from a shell; it
  delivers as before and logs a warning.
- The dashboard window checks HTTPS certificates. Pyloid turns those checks
  off for every page with `--ignore-certificate-errors` and
  `--allow-insecure-localhost`; the dashboard now removes both, since its UI
  is served over plain HTTP. Flags you set in `QTWEBENGINE_CHROMIUM_FLAGS` are
  kept as given.
- A deeply nested prompt or acknowledgment message no longer stops
  `vauxhall-relay` or the dashboard's MQTT connection; it is dropped like any
  other malformed message.
- The dashboard no longer logs the workspace path it copies to the clipboard.
- Hooks keep tool start times in an owner-only directory, as
  [privacy](https://github.com/ipapadop/vauxhall/blob/main/docs/privacy.md#on-disk)
  describes. The directory was readable by other accounts, and one that
  another account created first, or a symlink, was used as found, so that
  account could read tool timing or plant start times that faked a tool's
  duration. Such a directory is now refused with a warning, and the duration
  left out.
