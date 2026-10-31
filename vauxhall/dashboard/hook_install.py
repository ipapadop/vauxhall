# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Pick a workspace, run the hook installer in it, and stream its output."""

import logging
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from vauxhall.dashboard.ui_state import (
    INSTALL_DIRECTORY_KEY,
    load_ui_state,
    update_ui_state,
)
from vauxhall.hooks.agents import detect_agents

logger = logging.getLogger(__name__)

ALREADY_RUNNING = "An install is already running"


class HookInstallRunner:
    """Runs ``vauxhall-hook-install`` in a child process, one at a time.

    The child runs the installer CLI unchanged, in the workspace as its
    current directory, so the dashboard never changes its own. A daemon
    thread posts each output line as ``install-output`` and then
    ``install-done``.
    """

    def __init__(
        self,
        post: Callable[[str, object], None],
        *,
        select_directory: Callable[..., str | None],
        launch: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        """Initialize the runner.

        Args:
            post: Posts a window event without waiting; called from the
                reader thread.
            select_directory: Opens a directory picker at its ``dir``
                argument and returns the choice, or ``None`` when cancelled.
            launch: Starts the child, with ``subprocess.Popen``'s arguments.
        """
        self._post = post
        self._select_directory = select_directory
        self._launch = launch
        self._lock = threading.Lock()
        self._process: Any = None

    @property
    def running(self) -> bool:
        """Whether an install is running."""
        with self._lock:
            return self._process is not None

    def select_install_directory(self) -> dict[str, Any]:
        """Ask for a directory to install hooks into and detect its agents.

        Runs on the UI thread, like the other view-state writes. The picker
        opens at the last chosen directory, or at home once that is gone.

        Returns:
            ``ok`` with the chosen ``path`` and its ``agents``, or ``ok``
            false alone when cancelled.
        """
        last = load_ui_state().get(INSTALL_DIRECTORY_KEY)
        # Unlike Path.is_dir before Python 3.14, it is False on a
        # PermissionError, so an unreadable directory can't block the picker.
        start = last if last and os.path.isdir(last) else str(Path.home())  # noqa: PTH112
        chosen = self._select_directory(dir=start)
        if not chosen:
            return {"ok": False}
        try:
            update_ui_state({INSTALL_DIRECTORY_KEY: chosen})
        except OSError:
            logger.exception("Could not remember the install directory")
        return {"ok": True, "path": chosen, "agents": detect_agents(Path(chosen))}

    def install_hooks(self, directory: Path, agents: Sequence[str]) -> dict[str, Any]:
        """Start installing the hooks of some agents into a workspace.

        Args:
            directory: The workspace directory.
            agents: Agent keys the installer CLI accepts.

        Returns:
            ``{"ok": True}``, or ``ok`` false and an ``error``.
        """
        with self._lock:
            if self._process is not None:
                return {"ok": False, "error": ALREADY_RUNNING}
            try:
                # -u: a piped child buffers its output, which would arrive
                # in one burst at exit instead of as a live log. -X utf8: on
                # Windows a piped child writes the ANSI code page, which can't
                # encode every workspace path the installer prints. -P: -m
                # would put the workspace first on sys.path, so its own
                # vauxhall package or egg-info would replace the install's.
                process = self._launch(
                    [
                        sys.executable,
                        "-P",
                        "-u",
                        "-X",
                        "utf8",
                        "-m",
                        "vauxhall.hooks.cli",
                        *agents,
                    ],
                    cwd=directory,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as error:
                logger.exception("Could not start the hook installer")
                return {"ok": False, "error": str(error)}
            self._process = process
        threading.Thread(
            target=self._read, args=(process,), name="hook-install", daemon=True
        ).start()
        return {"ok": True}

    def _read(self, process: Any) -> None:  # noqa: ANN401
        """Post the child's output, then its result. Runs on the reader thread.

        Args:
            process: The running child.
        """
        returncode = None
        try:
            for line in process.stdout:
                self._post("install-output", {"line": line.rstrip("\r\n")})
            returncode = process.wait()
        except Exception:
            logger.exception("Could not read the hook installer's output")
        finally:
            # Cleared before the event, so a new install can start as soon
            # as the frontend sees this one finish.
            with self._lock:
                self._process = None
            self._post(
                "install-done", {"ok": returncode == 0, "returncode": returncode}
            )

    def close(self, timeout: float) -> None:
        """Stop a running install, killing it if it outlives the timeout.

        An interrupted install's venv is recovered by the next one.

        Args:
            timeout: Seconds to wait after terminating.
        """
        with self._lock:
            process = self._process
        if process is None:
            return
        process.terminate()
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Killing the hook installer, which didn't exit")
            process.kill()
