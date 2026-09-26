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
  session's tmux pane locally at `SessionStart`. Without MQTT authentication
  (issue #3), anyone who can publish to the broker can send prompts; see
  https://github.com/ipapadop/vauxhall/blob/main/docs/sending-prompts.md.
- Hooks for Claude Code, Codex, and Gemini CLI, installed with
  `vauxhall-hook-install claude codex gemini` into an isolated `.vauxhall-venv`.
- `TelemetryClient` and telemetry schema version 1 for other agents.
- JSON configuration files with environment variable overrides, validated at
  startup.
- Keyboard and screen reader support for every dashboard control.
- Documentation for a first run, configuration, privacy and the data each
  integration publishes, remote monitoring over SSH, troubleshooting, and
  uninstalling.
- A complete source distribution that can run every Python and frontend test.
- A tag-triggered release workflow that tests, builds, checks, and attaches
  the wheel and source distribution to a GitHub release.

### Fixed

- The Gemini CLI hook limits its MQTT connection attempt to 1 second, like the
  Claude Code and Codex hooks, instead of waiting longer when the broker is
  unreachable.
