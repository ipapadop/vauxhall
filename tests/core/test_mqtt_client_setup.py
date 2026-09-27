# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests that MQTT credentials and TLS settings take effect on the wire."""

import queue
import ssl
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt
import pytest
import trustme
from cryptography.hazmat.primitives import serialization

from tests.fake_broker import FakeBroker
from vauxhall.core.config import PASSWORD_ENV, MQTTConfig
from vauxhall.core.mqtt import configure_client
from vauxhall.dashboard.config import dashboard_settings
from vauxhall.dashboard.mqtt_client import DashboardSubscriber
from vauxhall.hooks.client import TelemetryClient
from vauxhall.hooks.config import hook_settings
from vauxhall.hooks.relay import PromptRelay


@dataclass
class Pki:
    """A throwaway certificate authority and the files derived from it.

    Attributes:
        ca: The authority.
        ca_file: Its certificate.
        server: A server certificate valid for ``localhost`` only.
        client_cert: A client certificate whose common name is ``agent-host``.
        client_key: The client certificate's key.
        other_key: A key that does not belong to the client certificate.
    """

    ca: trustme.CA
    ca_file: Path
    server: trustme.LeafCert
    client_cert: Path
    client_key: Path
    other_key: Path

    def server_context(self, *, require_client_cert: bool = False) -> ssl.SSLContext:
        """Build the TLS context a broker would use.

        Args:
            require_client_cert: Whether to demand a certificate signed by the CA.

        Returns:
            The server-side context.
        """
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.server.configure_cert(context)
        if require_client_cert:
            self.ca.configure_trust(context)
            context.verify_mode = ssl.CERT_REQUIRED
        return context

    def config(self, broker: FakeBroker, **overrides: object) -> MQTTConfig:
        """Build a TLS client configuration that trusts the CA.

        Args:
            broker: The broker to connect to.
            **overrides: Fields to set in place of the defaults.

        Returns:
            The client configuration.
        """
        fields: dict[str, object] = {
            "host": "localhost",
            "port": broker.port,
            "tls": True,
            "ca_certs": str(self.ca_file),
        }
        return MQTTConfig(**{**fields, **overrides})  # pyright: ignore[reportArgumentType]


@pytest.fixture
def pki(tmp_path: Path) -> Pki:
    """Create a certificate authority with a server and a client certificate.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        The authority and its files.
    """
    ca = trustme.CA()
    client = ca.issue_cert("client.example", common_name="agent-host")
    ca_file = tmp_path / "ca.pem"
    client_cert = tmp_path / "client.pem"
    client_key = tmp_path / "client.key"
    ca.cert_pem.write_to_path(str(ca_file))
    client.cert_chain_pems[0].write_to_path(str(client_cert))
    client.private_key_pem.write_to_path(str(client_key))
    other_key = tmp_path / "other.key"
    ca.issue_cert("other.example").private_key_pem.write_to_path(str(other_key))
    return Pki(
        ca, ca_file, ca.issue_cert("localhost"), client_cert, client_key, other_key
    )


@contextmanager
def connected(config: MQTTConfig) -> Iterator[None]:
    """Configure a client from ``config`` and keep it connected inside the block.

    Args:
        config: The configuration to connect with.

    Yields:
        Nothing; the client's network loop runs until the block exits.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    configure_client(client, config)
    client.connect(config.host, config.port)
    client.loop_start()
    try:
        yield
    finally:
        client.disconnect()
        client.loop_stop()


def test_no_credentials_are_sent_by_default() -> None:
    """A default configuration connects without a user name or password."""
    with FakeBroker() as broker, connected(MQTTConfig(port=broker.port)):
        attempt = broker.next_attempt()

    assert attempt.connect is not None
    assert attempt.connect.username is None
    assert attempt.connect.password is None


def test_password_from_environment_reaches_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user name and the environment password appear in CONNECT.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv(PASSWORD_ENV, "from-env")
    with (
        FakeBroker() as broker,
        connected(MQTTConfig(port=broker.port, username="agent-host")),
    ):
        attempt = broker.next_attempt()

    assert attempt.connect is not None
    assert (attempt.connect.username, attempt.connect.password) == (
        "agent-host",
        "from-env",
    )


def test_password_from_file_reaches_broker(tmp_path: Path) -> None:
    """The password file's content appears in CONNECT.

    Args:
        tmp_path: Pytest temporary directory.
    """
    password_file = tmp_path / "password"
    password_file.write_text("from-file\n", encoding="utf-8")
    with FakeBroker() as broker:
        config = MQTTConfig(
            port=broker.port, username="dashboard", password_file=str(password_file)
        )
        with connected(config):
            attempt = broker.next_attempt()

    assert attempt.connect is not None
    assert attempt.connect.password == "from-file"  # noqa: S105


def test_tls_connects_to_a_broker_the_ca_signed(pki: Pki) -> None:
    """A server certificate signed by the configured CA is accepted.

    Args:
        pki: The certificate authority and its files.
    """
    with FakeBroker(pki.server_context()) as broker, connected(pki.config(broker)):
        attempt = broker.next_attempt()

    assert attempt.connect is not None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ca_certs": ""}, "certificate verify failed"),
        ({"host": "127.0.0.1"}, "IP address mismatch"),
    ],
    ids=["untrusted-ca", "wrong-host-name"],
)
def test_tls_rejects_an_unverifiable_server(
    pki: Pki, overrides: dict[str, object], message: str
) -> None:
    """A server whose chain or name cannot be verified never gets a CONNECT.

    Args:
        pki: The certificate authority and its files.
        overrides: Client settings that break verification.
        message: Text the verification error must contain.
    """
    with FakeBroker(pki.server_context()) as broker:
        with (
            pytest.raises(ssl.SSLCertVerificationError, match=message),
            connected(pki.config(broker, **overrides)),
        ):
            pass
        attempt = broker.next_attempt()

    assert attempt.connect is None


def test_client_certificate_is_presented(pki: Pki) -> None:
    """A broker that demands a client certificate sees the configured one.

    Args:
        pki: The certificate authority and its files.
    """
    with FakeBroker(pki.server_context(require_client_cert=True)) as broker:
        config = pki.config(
            broker, certfile=str(pki.client_cert), keyfile=str(pki.client_key)
        )
        with connected(config):
            attempt = broker.next_attempt()

    assert attempt.connect is not None
    assert attempt.peer_common_name == "agent-host"


def test_broker_refuses_a_client_without_the_certificate(pki: Pki) -> None:
    """Omitting the client certificate leaves the handshake unfinished.

    Args:
        pki: The certificate authority and its files.
    """
    with FakeBroker(pki.server_context(require_client_cert=True)) as broker:
        # TLS 1.3 may report the refusal only on the first read.
        with suppress(ssl.SSLError, ConnectionError), connected(pki.config(broker)):
            pass
        attempt = broker.next_attempt()

    assert attempt.connect is None
    assert isinstance(attempt.error, ssl.SSLError)


def test_encrypted_client_key_fails_instead_of_prompting(
    pki: Pki, tmp_path: Path
) -> None:
    """A passphrase-protected key raises, since a hook cannot ask for one.

    Args:
        pki: The certificate authority and its files.
        tmp_path: Pytest temporary directory.
    """
    key = serialization.load_pem_private_key(pki.client_key.read_bytes(), password=None)
    encrypted = tmp_path / "client-encrypted.key"
    encrypted.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"passphrase"),
        )
    )
    config = MQTTConfig(tls=True, certfile=str(pki.client_cert), keyfile=str(encrypted))

    with pytest.raises(ssl.SSLError):
        configure_client(mqtt.Client(mqtt.CallbackAPIVersion.VERSION2), config)


def test_hook_client_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hooks' telemetry client connects with the hooks' credentials.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    with FakeBroker() as broker:
        monkeypatch.setattr(
            hook_settings, "mqtt", MQTTConfig(port=broker.port, username="agent-host")
        )
        with TelemetryClient() as client:
            attempt = broker.next_attempt()

            assert client.is_connected

    assert attempt.connect is not None
    assert attempt.connect.username == "agent-host"


@pytest.mark.parametrize("failure", ["missing-certificate", "mismatched-key"])
def test_hook_client_reports_failed_tls_setup_and_never_connects(
    pki: Pki,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    """When TLS setup fails, the hook client says so and does not connect at all.

    The files pass validation, then go wrong before the connection is made.

    Args:
        pki: The certificate authority and its files.
        monkeypatch: Pytest monkeypatch fixture.
        caplog: Pytest log capture fixture.
        failure: How the client certificate setup fails.
    """
    keyfile = pki.other_key if failure == "mismatched-key" else pki.client_key
    with FakeBroker() as broker:
        config = pki.config(broker, certfile=str(pki.client_cert), keyfile=str(keyfile))
        if failure == "missing-certificate":
            pki.client_cert.unlink()
        monkeypatch.setattr(hook_settings, "mqtt", config)

        with TelemetryClient() as client:
            assert not client.is_connected
        with pytest.raises(queue.Empty):
            broker.next_attempt(timeout=0.3)

    assert "Could not set up the broker connection" in caplog.text


def test_dashboard_subscriber_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dashboard's subscriber connects with the dashboard's credentials.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    with FakeBroker() as broker:
        monkeypatch.setattr(
            dashboard_settings, "mqtt", MQTTConfig(username="dashboard")
        )
        subscriber = DashboardSubscriber(MagicMock(), MagicMock(), port=broker.port)
        subscriber.start()
        try:
            attempt = broker.next_attempt()
        finally:
            subscriber.stop()

    assert attempt.connect is not None
    assert attempt.connect.username == "dashboard"


def test_dashboard_subscriber_reports_failed_tls_setup(
    pki: Pki, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key that does not match its certificate shows a status, not a crash.

    Args:
        pki: The certificate authority and its files.
        monkeypatch: Pytest monkeypatch fixture.
    """
    statuses: list[str] = []
    with FakeBroker() as broker:
        config = pki.config(
            broker, certfile=str(pki.client_cert), keyfile=str(pki.other_key)
        )
        monkeypatch.setattr(dashboard_settings, "mqtt", config)
        subscriber = DashboardSubscriber(MagicMock(), statuses.append, port=broker.port)

        subscriber.start()
        subscriber.stop()

        with pytest.raises(queue.Empty):
            broker.next_attempt(timeout=0.3)

    assert statuses[-1].startswith("Connection failed:")


def test_dashboard_subscriber_reports_a_password_file_it_cannot_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A password file that is not UTF-8 also shows a status, not a crash.

    ``password()`` raises ``UnicodeDecodeError`` for this, which is not an
    ``OSError``; ``configure_client`` must turn it into one so ``start()``'s
    ``except OSError`` still catches it.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    password_file = tmp_path / "password"
    password_file.write_bytes(b"\xff\xfe\x00bad")
    statuses: list[str] = []
    with FakeBroker() as broker:
        config = MQTTConfig(
            port=broker.port, username="dashboard", password_file=str(password_file)
        )
        monkeypatch.setattr(dashboard_settings, "mqtt", config)
        subscriber = DashboardSubscriber(MagicMock(), statuses.append, port=broker.port)

        subscriber.start()
        subscriber.stop()

        with pytest.raises(queue.Empty):
            broker.next_attempt(timeout=0.3)

    assert statuses[-1].startswith("Connection failed:")


def test_relay_propagates_a_password_file_it_cannot_decode_as_oserror(
    tmp_path: Path,
) -> None:
    """The relay's constructor sees an OSError, matching main()'s except clause.

    Args:
        tmp_path: Pytest temporary directory.
    """
    password_file = tmp_path / "password"
    password_file.write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(OSError, match="not valid UTF-8"):
        PromptRelay(MQTTConfig(username="agent-host", password_file=str(password_file)))


def test_relay_authenticates() -> None:
    """The relay connects with the credentials in the configuration it is given."""
    with FakeBroker() as broker:
        relay = PromptRelay(MQTTConfig(port=broker.port, username="agent-host"))
        relay.client.connect(relay.config.host, relay.config.port)
        relay.client.disconnect()
        attempt = broker.next_attempt()

    assert attempt.connect is not None
    assert attempt.connect.username == "agent-host"
