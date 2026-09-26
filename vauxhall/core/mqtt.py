# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""MQTT client setup shared by the dashboard, the hooks, and the relay."""

import ssl

import paho.mqtt.client as mqtt

from vauxhall.core.config import MQTTConfig


def configure_client(client: mqtt.Client, config: MQTTConfig) -> None:
    """Apply the configured credentials and TLS settings to a client.

    TLS always verifies the server certificate chain and host name; there is
    no way to turn that off.

    Args:
        client: The client to configure before it connects.
        config: The MQTT configuration to apply.

    Raises:
        OSError: If the password file or a certificate file cannot be read.
        ssl.SSLError: If the client certificate and key do not match, or the
            key is encrypted.
    """
    if config.username:
        client.username_pw_set(config.username, config.password())
    if config.tls:
        context = ssl.create_default_context(cafile=config.ca_certs or None)
        if config.certfile:
            # A callback that returns nothing makes an encrypted key fail
            # instead of prompting for a passphrase in a non-interactive hook.
            context.load_cert_chain(
                config.certfile, config.keyfile, password=lambda: b""
            )
        client.tls_set_context(context)
