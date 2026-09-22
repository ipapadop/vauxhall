<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Troubleshooting

Two tools find most problems. `mosquitto_sub`, which ships with Mosquitto,
shows every message that reaches the broker:

```bash
mosquitto_sub -h localhost -t 'vauxhall/agents/#' -v
```

And every hook can be run by hand, with debug logging, from the workspace:

```bash
echo '{"hook_event_name": "Stop", "session_id": "test", "cwd": "'"$PWD"'"}' |
  VAUXHALL_LOGGING_LEVEL=DEBUG \
  .vauxhall-venv/bin/python -m vauxhall.hooks.claude.telemetry_hook
```

It prints `{}` on stdout and logs to stderr either
`Successfully sent telemetry ...` or `Failed to connect telemetry client ...`.
Replace `claude` with `codex` or `gemini` to run the other hooks.

## Broker connection

**The dashboard's status line keeps retrying.** The dashboard can't reach the
broker at `mqtt.host`:`mqtt.port` (`localhost:1883` by default).

- Check that Mosquitto is running: `mosquitto -v` in a terminal, or
  `systemctl status mosquitto` if it runs as a service.
- Check that something listens on the port: `ss -ltn | grep 1883` on Linux,
  `lsof -iTCP:1883 -sTCP:LISTEN` on macOS, or
  `Get-NetTCPConnection -LocalPort 1883` in PowerShell.
- If the broker is on another machine, it listens only on that machine's
  loopback, as it should. Use an SSH tunnel as described in
  [remote-deployment.md](remote-deployment.md).

**Mosquitto says `Address already in use`.** Another broker, often the system
service installed with the package, already has the port. Use that one, or stop
it first.

**Hooks report `Failed to connect telemetry client`.** The same checks apply
on the agent machine. The hooks read their own configuration, not the
dashboard's: check `VAUXHALL_MQTT_HOST` and `VAUXHALL_MQTT_PORT`, a
`vauxhall_hooks.json` in the workspace, and `~/.config/vauxhall/vauxhall_hooks.json`,
in that order. If the dashboard's settings dialog changed the broker, check
**Also update hooks configuration** to copy the change to the hooks.

## Dashboard startup

**`No matching distribution found for pyside6`** while installing. The
dashboard needs a platform that PySide6 6.9.2 ships wheels for; see the
[compatibility table](../README.md#compatibility). Python 3.14, Intel Macs
older than macOS 12, and ARM64 Linux older than glibc 2.39 aren't supported.
The hooks install anywhere.

**The dashboard exits with a Qt error on Linux**, such as
`libEGL.so.1: cannot open shared object file` or
`Could not load the Qt platform plugin "xcb"`. Qt needs system libraries that
minimal installations lack. On Ubuntu 24.04 or Debian 13:

```bash
sudo apt install libegl1 libgl1 libgbm1 libnss3 libasound2t64 libdbus-1-3 \
  libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcomposite1 libxdamage1 \
  libxi6 libxkbfile1 libxrandr2 libxshmfence1 libxtst6
```

On older releases, install `libasound2` instead of `libasound2t64`. Run
`QT_DEBUG_PLUGINS=1 vauxhall` to see which library is missing. The dashboard
is a desktop window: it needs a graphical session, and doesn't run over plain
SSH.

**The dashboard stops with `Invalid configuration value`.** The message names
the environment variable or file, the field, the value, and what is expected.
Fix or remove that value; see [configuration.md](configuration.md).

**The dashboard fails to start and port 8080 is busy.** `dashboard.port` is
the port of the dashboard's local UI server. Pick a free one with
`VAUXHALL_DASHBOARD_PORT=8181 vauxhall`.

## Hooks

**No card appears for an agent.**

1. Run `mosquitto_sub` as above and use the agent. If messages appear, the
   dashboard isn't connected to the same broker.
2. If nothing appears, run the hook by hand as above.
3. If that works, the agent isn't running the hooks. Check the agent's
   settings file for handlers that run `vauxhall.hooks.<agent>.telemetry_hook`
   and restart the agent. Each agent reads its hooks at startup, and Codex
   also needs them trusted (see below).

**The hook logs `Skipping telemetry: no stable session identity is
available`.** The event had no session ID or transcript path. Set
`VAUXHALL_SESSION_ID` in the agent's environment to a value that is unique per
session.

**The hook command fails with `No such file or directory`.** The workspace
was moved, or `.vauxhall-venv` was deleted or built with a Python that has
since been removed. Run `vauxhall-hook-install <agents>` again in the
workspace; it rebuilds the environment and rewrites the commands.

**`vauxhall-hook-install` exits with an error about the settings file.** The
agent's settings file is not valid JSON, or has an unexpected structure. The
installer leaves every file unchanged; fix the file it names and run it again.
The installer also needs network access, to install Vauxhall into
`.vauxhall-venv` from PyPI, Git, or a local path.

**Cards appear but some events are missing.** Each hook has a 3-second timeout
and waits up to one second for the broker. On a slow link some events can be
dropped; the agent is never blocked. See the known gaps for each agent in
[integrations.md](integrations.md), for example that Claude Code has no
interrupt event.

## Trust and permission prompts

- **Claude Code** reads hooks from `.claude/settings.local.json` at startup.
  Restart it, or open `/hooks` to review the registered hooks.
- **Codex** runs project hooks only after you trust them. Open `/hooks`,
  review the Vauxhall hooks, and trust them. Running the installer again
  changes the hook definitions, so Codex asks again.
- **Gemini CLI** ignores a workspace's `.gemini/settings.json`, including its
  hooks, in a folder it doesn't trust. Trust the folder when Gemini CLI asks.
