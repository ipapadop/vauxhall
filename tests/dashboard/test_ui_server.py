# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the dashboard's UI server."""

import errno
import http.client
import socket
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from vauxhall.dashboard.ui_server import CONTENT_SECURITY_POLICY, UIServer


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
    """The URL points at the page the window loads, on the port actually bound."""
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
    """Types come from the server, not the platform's MIME table."""
    response = get(server, path)

    assert response.status == 200
    assert response.getheader("Content-Type") == content_type
    assert response.getheader("Content-Security-Policy") == CONTENT_SECURITY_POLICY


@pytest.mark.parametrize(
    "path",
    [
        "/missing.js",
        "/secret.py",
        "/js",
        "/../outside.js",
        "/js/../../outside.js",
        "/%2e%2e/outside.js",
    ],
)
def test_refuses_missing_unknown_and_outside_files(server: UIServer, path: str) -> None:
    """Only files of a served type inside the directory are returned."""
    assert get(server, path).status == 404


def test_refuses_a_port_another_socket_listens_on(
    ui_dir: Path, listening_port: int
) -> None:
    """A taken port raises at once instead of loading another program's page."""
    try:
        UIServer(ui_dir, listening_port)
    except OSError as error:
        refused = error
    else:
        pytest.fail("bound a port another socket listens on")

    # Windows reports an exclusively held port as WSAEACCES.
    assert refused.errno in {errno.EADDRINUSE, errno.EACCES}


def test_close_stops_serving(ui_dir: Path) -> None:
    """After close, the port no longer accepts connections."""
    server = UIServer(ui_dir, 0)
    parts = urlsplit(server.url)
    assert get(server, "/").status == 200

    server.close(1.0)

    with pytest.raises((ConnectionRefusedError, TimeoutError)):
        socket.create_connection((parts.hostname, parts.port), timeout=1).close()
