# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Serve the dashboard UI on a loopback port the dashboard holds alone."""

import asyncio
import logging
import socket
import sys
import threading
from pathlib import Path

from aiohttp import web

logger = logging.getLogger(__name__)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'"
)

# Time for the loop to stop once cleanup ends or is cancelled.
_STOP_GRACE_SECONDS = 0.1

# Fixed rather than guessed: on Windows the registry can map .js to
# text/plain, which stops a module script from loading.
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def _bind(port: int) -> socket.socket:
    """Bind a listening socket on ``127.0.0.1:port`` that no one else holds.

    Windows lets a second socket bind a port held with ``SO_REUSEADDR``, so
    the port is held exclusively there. On Linux ``SO_REUSEADDR`` only lets a
    restart bind past connections in ``TIME_WAIT``; on macOS and the BSDs it
    would also bind beside another program listening on ``*:port``, so it is
    left off there.

    Args:
        port: The port, or 0 for one the system picks.

    Returns:
        The listening socket.

    Raises:
        OSError: The port can't be bound, such as when it is in use.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif sys.platform.startswith("linux"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen()
    except OSError:
        sock.close()
        raise
    return sock


class UIServer:
    """Serves a directory's UI files over HTTP from a daemon thread."""

    def __init__(self, directory: Path, port: int) -> None:
        """Bind the port and start serving.

        Args:
            directory: The directory holding ``index.html`` and its assets.
            port: The port, or 0 for one the system picks.

        Raises:
            OSError: The port can't be bound.
        """
        self._root = directory.resolve()
        sock = _bind(port)
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}/index.html"

        app = web.Application()
        app.router.add_get("/{path:.*}", self._handle)
        app.on_response_prepare.append(_add_policy)
        self._runner = web.AppRunner(app, access_log=None)
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._start(sock))
        except BaseException:
            sock.close()
            self._loop.close()
            raise
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="vauxhall-ui-server", daemon=True
        )
        self._thread.start()

    async def _start(self, sock: socket.socket) -> None:
        """Start the server on the bound socket.

        Args:
            sock: The listening socket.
        """
        await self._runner.setup()
        await web.SockSite(self._runner, sock).start()

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        """Return a UI file, or 404 for anything else.

        Args:
            request: The request; its path is relative to the directory.

        Returns:
            The file.

        Raises:
            web.HTTPNotFound: The path is outside the directory, not a file,
                or not of a served type.
        """
        try:
            path = (self._root / (request.match_info["path"] or "index.html")).resolve()
            found = path.is_relative_to(self._root) and path.is_file()
        except (OSError, ValueError) as error:  # ValueError: an encoded NUL
            raise web.HTTPNotFound from error
        content_type = _CONTENT_TYPES.get(path.suffix)
        if not found or not content_type:
            raise web.HTTPNotFound
        return web.FileResponse(path, headers={"Content-Type": content_type})

    def close(self, timeout: float) -> None:
        """Stop serving and release the port.

        Args:
            timeout: Seconds to wait for the server to stop.
        """
        asyncio.run_coroutine_threadsafe(self._stop(timeout), self._loop)
        self._thread.join(timeout + _STOP_GRACE_SECONDS)
        if self._thread.is_alive():
            logger.warning("The UI server didn't stop within %s seconds", timeout)
        else:
            self._loop.close()

    async def _stop(self, seconds: float) -> None:
        """Clean up the server within ``seconds``, then stop the loop.

        A request still in flight at the timeout is cancelled, as
        ``asyncio.run`` does on exit, so no task outlives the loop.

        Args:
            seconds: Time to allow the cleanup.
        """
        try:
            await asyncio.wait_for(self._runner.cleanup(), seconds)
        except Exception:
            logger.exception("Could not stop the UI server cleanly")
        finally:
            others = asyncio.all_tasks() - {asyncio.current_task()}
            for task in others:
                task.cancel()
            await asyncio.gather(*others, return_exceptions=True)
            asyncio.get_running_loop().stop()


async def _add_policy(_request: web.Request, response: web.StreamResponse) -> None:
    """Add the content security policy, and no-cache so edits load, to responses.

    Args:
        _request: The request being answered.
        response: The response about to be sent.
    """
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["Cache-Control"] = "no-cache"
