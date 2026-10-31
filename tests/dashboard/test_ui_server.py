# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the dashboard's UI server."""

import asyncio
import errno
import http.client
import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from vauxhall.dashboard.ui_server import CONTENT_SECURITY_POLICY, UIServer, _bind


@pytest.fixture
def ui_dir(tmp_path: Path) -> Path:
    """A UI directory with one file of each served type and one that isn't.

    Args:
        tmp_path: Pytest's per-test directory.

    Returns:
        The directory to serve.
    """
    root = tmp_path / "ui"
    (root / "js").mkdir(parents=True)
    (root / "index.html").write_text("<!DOCTYPE html><title>t</title>")
    (root / "js" / "app.js").write_text("export {};")
    (root / "secret.py").write_text("SECRET = 1")
    (tmp_path / "outside.js").write_text("export {};")
    return root


@pytest.fixture
def server(ui_dir: Path) -> Iterator[UIServer]:
    """A running server on a free port, closed after the test.

    Args:
        ui_dir: The directory to serve.

    Yields:
        The server.
    """
    running = UIServer(ui_dir, 0)
    try:
        yield running
    finally:
        running.close(1.0)


def get(server: UIServer, path: str) -> http.client.HTTPResponse:
    """Send a raw GET, so the path reaches the server unnormalized.

    Args:
        server: The server to ask.
        path: The request target, sent as is.

    Returns:
        The response, with its body read.
    """
    parts = urlsplit(server.url)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    response.read()
    connection.close()
    return response


def test_url_names_the_loopback_address_and_bound_port(server: UIServer) -> None:
    """The URL points at the page the window loads, on the port actually bound.

    Args:
        server: The running server.
    """
    parts = urlsplit(server.url)

    assert parts.hostname == "127.0.0.1"
    assert parts.port not in (None, 0)
    assert parts.path == "/index.html"


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/", "text/html; charset=utf-8"),
        ("/index.html", "text/html; charset=utf-8"),
        ("/js/app.js", "text/javascript; charset=utf-8"),
    ],
)
def test_serves_ui_files_with_fixed_types_and_the_csp(
    server: UIServer, path: str, content_type: str
) -> None:
    """Types come from the server, not the platform's MIME table.

    Args:
        server: The running server.
        path: The request path.
        content_type: The expected Content-Type.
    """
    response = get(server, path)

    assert response.status == 200
    assert response.getheader("Content-Type") == content_type
    assert response.getheader("Content-Security-Policy") == CONTENT_SECURITY_POLICY
    assert response.getheader("Cache-Control") == "no-cache"


@pytest.mark.parametrize(
    "path",
    [
        "/missing.js",
        "/secret.py",
        "/js",
        "/../outside.js",
        "/js/../../outside.js",
        "/%2e%2e/outside.js",
        "/%00",
        "/js/a%00.js",
    ],
)
def test_refuses_missing_unknown_and_outside_files(server: UIServer, path: str) -> None:
    """Only files of a served type inside the directory are returned.

    Args:
        server: The running server.
        path: The request path, sent unnormalized.
    """
    assert get(server, path).status == 404


def test_refuses_a_port_another_socket_listens_on(
    ui_dir: Path, listening_port: int
) -> None:
    """A taken port raises at once instead of loading another program's page.

    Args:
        ui_dir: The directory to serve.
        listening_port: A port another socket listens on.
    """
    try:
        UIServer(ui_dir, listening_port)
    except OSError as error:
        refused = error
    else:
        pytest.fail("bound a port another socket listens on")

    # Windows reports an exclusively held port as WSAEACCES.
    assert refused.errno in {errno.EADDRINUSE, errno.EACCES}


def test_close_stops_serving(ui_dir: Path) -> None:
    """After close, the port no longer accepts connections.

    Args:
        ui_dir: The directory to serve.
    """
    server = UIServer(ui_dir, 0)
    parts = urlsplit(server.url)
    assert get(server, "/").status == 200

    server.close(1.0)

    with pytest.raises((ConnectionRefusedError, TimeoutError)):
        socket.create_connection((parts.hostname, parts.port), timeout=1).close()


def test_close_returns_within_its_timeout_when_a_request_is_stuck(
    ui_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A client that stops reading can't stretch shutdown or leave tasks behind.

    A task left pending on the closed loop is reported as destroyed later.

    Args:
        ui_dir: The directory to serve.
        caplog: Captures the cleanup error.
    """
    (ui_dir / "big.js").write_bytes(b"x" * 16_000_000)
    server = UIServer(ui_dir, 0)
    parts = urlsplit(server.url)
    with socket.create_connection((parts.hostname, parts.port)) as client:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        client.sendall(b"GET /big.js HTTP/1.1\r\nHost: localhost\r\n\r\n")
        client.recv(1)
        started = time.monotonic()

        server.close(0.5)
        elapsed = time.monotonic() - started

    assert elapsed < 0.8
    assert "Could not stop the UI server cleanly" in caplog.text
    assert not asyncio.all_tasks(server._loop)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows holds the port exclusively"
)
def test_bind_allows_reuse_past_time_wait_only_on_linux() -> None:
    """Elsewhere SO_REUSEADDR would let the bind share a wildcard listener's port."""
    sock = _bind(0)
    try:
        reuse = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
    finally:
        sock.close()

    assert bool(reuse) is sys.platform.startswith("linux")
