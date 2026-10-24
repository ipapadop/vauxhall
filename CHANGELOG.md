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

### Security

- The prompt relay no longer types a prompt into a shell. An agent that
  exited without ending its session, for example after a crash, left the
  shell in its tmux pane, and the relay pasted the prompt there, where it ran
  as a command. Hooks now record the pane's foreground command at session
  start, and the relay refuses delivery (`pane-unavailable`) when the pane
  runs something else. Sessions started before upgrading keep the old
  behavior until they start again.
- The dashboard window checks HTTPS certificates. Pyloid turns those checks
  off for every page with `--ignore-certificate-errors` and
  `--allow-insecure-localhost`; the dashboard now removes both, since its UI
  is served over plain HTTP. Flags you set in `QTWEBENGINE_CHROMIUM_FLAGS` are
  kept as given.
- A deeply nested prompt or acknowledgment message no longer stops
  `vauxhall-relay` or the dashboard's MQTT connection; it is dropped like any
  other malformed message.
- The dashboard no longer logs the workspace path it copies to the clipboard.
