# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""A minimal MQTT 3.1.1 listener that records how clients connect."""

import queue
import socket
import ssl
import threading
from dataclasses import dataclass
from types import TracebackType
from typing import TypeVar

_BrokerT = TypeVar("_BrokerT", bound="FakeBroker")

_CONNACK_ACCEPTED = b"\x20\x02\x00\x00"


@dataclass(frozen=True)
class Connect:
    """The fields of an MQTT CONNECT packet that tests inspect.

    Attributes:
        client_id: The client identifier.
        username: The user name, or ``None`` when the client sent none.
        password: The password, or ``None`` when the client sent none.
    """

    client_id: str
    username: str | None
    password: str | None


@dataclass(frozen=True)
class Attempt:
    """One incoming connection.

    Attributes:
        connect: The CONNECT packet, or ``None`` when the TLS handshake failed.
        error: The handshake failure, if any.
        peer_common_name: The common name of the client certificate, if any.
    """

    connect: Connect | None
    error: OSError | None
    peer_common_name: str | None


def _read_exactly(sock: socket.socket, size: int) -> bytes:
    """Read exactly ``size`` bytes from a socket.

    Args:
        sock: The socket to read from.
        size: The number of bytes to read.

    Returns:
        The bytes read.

    Raises:
        ConnectionError: If the peer closes the connection first.
    """
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            message = "connection closed before the packet was complete"
            raise ConnectionError(message)
        data += chunk
    return data


def _read_connect(sock: socket.socket) -> Connect:
    """Read and decode one CONNECT packet.

    Args:
        sock: The socket to read from.

    Returns:
        The decoded packet.
    """
    assert _read_exactly(sock, 1) == b"\x10"
    length, multiplier = 0, 1
    while True:
        byte = _read_exactly(sock, 1)[0]
        length += (byte & 0x7F) * multiplier
        multiplier *= 128
        if not byte & 0x80:
            break
    body = _read_exactly(sock, length)

    position = 0

    def read_string() -> str:
        nonlocal position
        size = int.from_bytes(body[position : position + 2], "big")
        text = body[position + 2 : position + 2 + size].decode()
        position += 2 + size
        return text

    read_string()  # protocol name
    flags = body[position + 1]
    position += 4  # level, flags, keepalive
    client_id = read_string()
    username = read_string() if flags & 0x80 else None
    password = read_string() if flags & 0x40 else None
    return Connect(client_id, username, password)


class FakeBroker:
    """Accepts connections on a free loopback port and records each one.

    It completes an optional TLS handshake, reads the CONNECT packet, and
    answers with an accepted CONNACK.
    """

    def __init__(self, tls: ssl.SSLContext | None = None) -> None:
        """Start listening.

        Args:
            tls: Server-side TLS context, or ``None`` for plaintext.
        """
        self._tls = tls
        self._attempts: queue.Queue[Attempt] = queue.Queue()
        self._listener = socket.create_server(("127.0.0.1", 0))
        # Closing a listening socket does not wake a blocked accept, so poll.
        self._listener.settimeout(0.05)
        self._stopped = threading.Event()
        self.host, self.port = self._listener.getsockname()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def __enter__(self: _BrokerT) -> _BrokerT:  # noqa: PYI019
        """Enter the context.

        Returns:
            The broker.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop listening.

        Args:
            exc_type: Type of the exception leaving the block, if any.
            exc_val: The exception leaving the block, if any.
            exc_tb: Traceback of the exception leaving the block, if any.
        """
        self._stopped.set()
        self._thread.join(timeout=5)
        self._listener.close()

    def next_attempt(self, timeout: float = 5.0) -> Attempt:
        """Wait for the next connection attempt to finish.

        Args:
            timeout: Seconds to wait.

        Returns:
            The attempt.

        Raises:
            queue.Empty: If nothing connected in time.
        """
        return self._attempts.get(timeout=timeout)

    def _serve(self) -> None:
        """Handle connections until the broker is stopped."""
        while not self._stopped.is_set():
            try:
                sock, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with sock:
                self._attempts.put(self._handle(sock))

    def _handle(self, sock: socket.socket) -> Attempt:
        """Read one connection's CONNECT packet.

        Args:
            sock: The accepted socket.

        Returns:
            What the client presented.
        """
        sock.settimeout(5)
        common_name = None
        try:
            if self._tls is not None:
                sock = self._tls.wrap_socket(sock, server_side=True)
                if certificate := sock.getpeercert():
                    common_name = next(
                        value
                        for rdn in certificate["subject"]
                        for key, value in rdn
                        if key == "commonName"
                    )
            connect = _read_connect(sock)
            sock.sendall(_CONNACK_ACCEPTED)
        except OSError as error:
            return Attempt(None, error, common_name)
        return Attempt(connect, None, common_name)
