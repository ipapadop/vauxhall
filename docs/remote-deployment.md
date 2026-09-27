<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Monitoring Agents on Other Machines

To watch agents on other machines, either keep the broker on loopback and
carry the connection over SSH (below), or run a broker on the network that
requires TLS and passwords, see [Networked brokers](#networked-brokers). An
unauthenticated broker must never listen on a network interface.

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

Vauxhall connects to a broker on a shared host or public address with TLS and
a user name and password. TLS always verifies the broker's certificate chain
and host name; there is no setting to skip that. Use one broker identity per
role, and let the broker's ACL decide who may publish prompts, because a
prompt can make an agent run commands.

This example uses Mosquitto. The broker's certificate must name the host that
Vauxhall connects to.

```conf
# mosquitto.conf
listener 8883
cafile /etc/mosquitto/certs/ca.pem
certfile /etc/mosquitto/certs/server.pem
keyfile /etc/mosquitto/certs/server.key
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl
```

```bash
mosquitto_passwd -c /etc/mosquitto/passwd dashboard
mosquitto_passwd /etc/mosquitto/passwd agent-host
```

```conf
# /etc/mosquitto/acl
user dashboard
topic read vauxhall/agents/+/activity
topic read vauxhall/agents/+/status
topic read vauxhall/agents/+/sessions/+/ack
topic write vauxhall/agents/+/sessions/+/prompt

user agent-host
topic write vauxhall/agents/+/activity
topic write vauxhall/agents/+/sessions/+/ack
topic read vauxhall/agents/+/sessions/+/prompt
```

With this ACL only the `dashboard` identity can send prompts, and `agent-host`
can publish telemetry and read prompts but can't read other agents' telemetry.
Give each agent machine its own identity if you want to revoke one without
affecting the others.

Store each password in a file that only your account can read, and point the
client at it. Hooks are started by the agent, which may not pass your shell's
environment on, so a file is more reliable than `VAUXHALL_MQTT_PASSWORD`:

```bash
install -m 600 /dev/null ~/.config/vauxhall/mqtt-password
printf '%s\n' 'the-password' > ~/.config/vauxhall/mqtt-password
```

On the dashboard machine, `~/.config/vauxhall/vauxhall_dashboard.json`:

```json
{
  "mqtt": {
    "host": "broker.example.com",
    "port": 8883,
    "tls": true,
    "ca_certs": "/home/me/.config/vauxhall/ca.pem",
    "username": "dashboard",
    "password_file": "/home/me/.config/vauxhall/mqtt-password"
  }
}
```

On each agent machine, the same in `vauxhall_hooks.json` with
`"username": "agent-host"`. `vauxhall-relay` reads it too. Omit `ca_certs` when
the broker's certificate is signed by a public authority in the system trust
store.

To authenticate with a client certificate instead of, or as well as, a
password, set `certfile` and `keyfile` and have the broker require one
(`require_certificate true` in Mosquitto). The key can't be protected by a
passphrase, because hooks can't prompt for it; restrict its file permissions
instead.

Paths must be absolute, because hooks run in the agent's working directory. A
path that is relative, doesn't exist, or can't be read stops the dashboard at
startup, and makes hooks report the error on stderr. A certificate and key that
don't match, or a key that is encrypted, show in the dashboard's status line as
a failed connection and in the hooks' stderr.

A wrong password or an untrusted certificate also shows in the dashboard's
status line as a failed connection. Hooks drop their telemetry silently, as
they do whenever the broker is unreachable; run the
[tunnel check](#checking-the-tunnel) snippet, without the tunnel, to test a
hooks configuration.
