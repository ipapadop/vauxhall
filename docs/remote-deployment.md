<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Monitoring Agents on Other Machines

Vauxhall's MQTT connection has no authentication or encryption yet (issue #3),
so the broker must never listen on a network interface. To watch agents on
other machines, keep the broker on loopback and carry the connection over SSH,
which authenticates both ends and encrypts the traffic.

Read [privacy.md](privacy.md) first: everything the hooks publish crosses the
tunnel and is readable by anyone who can reach the broker.

## Local development

When the dashboard and the agents run on the same machine, there is nothing to
set up: start `mosquitto` and use the defaults, as in the
[first run](../README.md#first-run). Mosquitto 2 listens only on
`127.0.0.1:1883` when started without a configuration file.

## Broker on the dashboard machine

To keep the broker on loopback explicitly, even if a system-wide
configuration exists, start it with a configuration file of its own:

```conf
# vauxhall-mosquitto.conf
listener 1883 127.0.0.1
allow_anonymous true
```

```bash
mosquitto -c vauxhall-mosquitto.conf
```

`allow_anonymous true` is safe only because the listener is on loopback.

## Forwarding the port over SSH

Pick the direction that matches which machine can open an SSH connection to
the other. Either way, the agent machine ends up with the dashboard's broker on
its own `localhost:1883`, so the hooks' defaults work unchanged.

**The dashboard machine can SSH to the agent machine** (for example, a laptop
running the dashboard and a remote development server running the agents).
On the dashboard machine, run:

```bash
ssh -N -R 127.0.0.1:1883:127.0.0.1:1883 user@agent-host
```

**The agent machine can SSH to the dashboard machine.** On the agent machine,
run:

```bash
ssh -N -L 127.0.0.1:1883:127.0.0.1:1883 user@dashboard-host
```

If port 1883 is already taken on the agent machine, forward another local
port, such as `11883`, and point the hooks at it with
`VAUXHALL_MQTT_PORT=11883` or a `vauxhall_hooks.json` (see
[configuration.md](configuration.md)).

Keep the tunnel running while the agents work, for example with
`autossh -M 0 -N ...` or a systemd user service. While it is down, the hooks
drop their telemetry after a one-second connection attempt and the agents keep
working; the dashboard's cards go stale.

### Checking the tunnel

On the agent machine, with the tunnel up, publish a test event:

```bash
.vauxhall-venv/bin/python - <<'EOF'
from uuid import uuid4
from vauxhall.hooks.client import TelemetryClient

delivered = TelemetryClient().send(
    agent="Tunnel test",
    workspace="/tmp",
    session_id=str(uuid4()),
    state="Idle",
    env="remote",
    status="Tunnel works",
)
print("delivered" if delivered else "not delivered")
EOF
```

`delivered` means the dashboard's broker acknowledged the message, and a
**Tunnel test** card appears on the dashboard.

## Sending prompts to remote agents

Run `vauxhall-relay` on the agent machine, through the same tunnel; it reads
the hooks' broker settings, so `localhost:1883` reaches the dashboard's broker.
See [sending-prompts.md](sending-prompts.md). Anyone who can reach the tunnel's
port on the agent machine can send prompts too.

## What the tunnel doesn't protect

- On the agent machine, the forwarded port is on loopback, so other accounts on
  that machine can connect to it and read or publish telemetry, including
  prompts for your agents. Use the tunnel
  only on machines you don't share, or where you trust every account.
- The same applies to the broker's loopback port on the dashboard machine.
- The dashboard labels workspaces under `/home` as LOCAL even when they are on
  a remote machine; hooks don't set the `env` field.

## Networked brokers

Running Mosquitto on a shared host or a public address needs username and
password authentication and TLS in Vauxhall's client, which issue #3 adds.
Until then, don't expose a broker that Vauxhall connects to.
