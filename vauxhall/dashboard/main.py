# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Main entry point for the Vauxhall Dashboard application."""

import os
import sys
from collections.abc import MutableMapping
from contextlib import suppress
from pathlib import Path

from pyloid import Pyloid
from PySide6.QtCore import QLockFile

from vauxhall.core.config_store import user_config_path
from vauxhall.core.logging import get_logger, setup_logging
from vauxhall.dashboard import USER_CHROMIUM_FLAGS
from vauxhall.dashboard.app import SHUTDOWN_CLOSE_SECONDS, UI_DIR, DashboardApp
from vauxhall.dashboard.config import dashboard_settings as settings
from vauxhall.dashboard.graphics import set_graphics_backend
from vauxhall.dashboard.ui_server import UIServer

logger = get_logger(__name__)

# Held while a dashboard runs: two would overwrite each other's saved state.
INSTANCE_LOCK_FILE = "dashboard.lock"


def _use_utf8_output() -> None:
    """Keep non-ASCII output from killing whoever writes it.

    The UI server prints a banner containing emoji. Windows consoles default to
    a code page that cannot represent them, and the resulting UnicodeEncodeError
    stops the server before it serves anything.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            with suppress(AttributeError, OSError, ValueError):
                stream.reconfigure(  # pyright: ignore[reportAttributeAccessIssue]
                    encoding="utf-8", errors="replace"
                )


# Pyloid turns off certificate checks for every page the window loads. The UI
# is served over plain HTTP, so they serve no purpose here.
_INSECURE_PYLOID_FLAGS = frozenset(
    {"--ignore-certificate-errors", "--allow-insecure-localhost"}
)


def _set_chromium_flags(
    environ: MutableMapping[str, str] = os.environ,
    user_flags: str = USER_CHROMIUM_FLAGS,
) -> None:
    """Drop Pyloid's certificate overrides and append the user's flags.

    Qt reads the variable when the application starts, so this must run
    before ``Pyloid``. The user's flags are kept as given.

    Args:
        environ: The environment to update.
        user_flags: The flags the user set before Pyloid's import.
    """
    pyloid_flags = environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    flags = [flag for flag in pyloid_flags if flag not in _INSECURE_PYLOID_FLAGS]
    environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([*flags, user_flags]).strip()


def _lock_dashboard(path: Path) -> QLockFile:
    """Lock ``path`` for this dashboard, refusing to run beside another one.

    A lock whose process has exited is taken over. When the lock can't be
    created at all, the dashboard runs without it rather than not at all.

    Args:
        path: The lock file.

    Returns:
        The lock, held until it is unlocked or the process exits.

    Raises:
        SystemExit: Another live process holds the lock.
    """
    with suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path))
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        return lock
    if lock.error() == QLockFile.LockError.LockFailedError:
        pid, host, _ = lock.getLockInfo()
        logger.error(
            "Another Vauxhall Dashboard is already running (process %s on %s); "
            "if it isn't, delete %s",
            pid,
            host or "unknown host",
            path,
        )
        raise SystemExit(1)
    logger.warning(
        "Could not create %s (%s); a second dashboard would not be refused",
        path,
        lock.error().name,
    )
    return lock


def _serve_ui(port: int) -> UIServer:
    """Serve the UI on ``port``, refusing to run when the port is taken.

    Loading the page from a port another program holds would hand that
    program's page the dashboard's bridge.

    Args:
        port: The configured UI port.

    Returns:
        The running server.

    Raises:
        SystemExit: The port can't be bound.
    """
    try:
        server = UIServer(UI_DIR, port)
    except OSError as error:
        logger.exception(
            "Could not serve the dashboard UI on 127.0.0.1:%s; another program "
            "may be using the port. Set dashboard.port to a free port",
            port,
        )
        raise SystemExit(1) from error
    logger.info("Serving UI from %s at %s", UI_DIR, server.url)
    return server


def main() -> None:
    """Run the Vauxhall Dashboard application."""
    _use_utf8_output()
    _set_chromium_flags()
    setup_logging(level=settings.logging.level)
    lock = _lock_dashboard(user_config_path(INSTANCE_LOCK_FILE))
    logger.info("Starting Vauxhall Dashboard...")
    set_graphics_backend(settings.dashboard.graphics_backend)

    app = Pyloid(app_name="Vauxhall Dashboard")
    try:
        ui_server = _serve_ui(settings.dashboard.port)
        try:
            DashboardApp(app).run(ui_server.url)
        finally:
            ui_server.close(SHUTDOWN_CLOSE_SECONDS)
    finally:
        lock.unlock()


if __name__ == "__main__":
    main()
