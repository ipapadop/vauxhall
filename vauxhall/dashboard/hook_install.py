# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Run the hook installer for a workspace and stream its output."""

import logging
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

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
        launch: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        """Initialize the runner.

        Args:
            post: Posts a window event without waiting; called from the
                reader thread.
            launch: Starts the child, with ``subprocess.Popen``'s arguments.
        """
        self._post = post
        self._launch = launch
        self._lock = threading.Lock()
        self._process: Any = None

    @property
    def running(self) -> bool:
        """Whether an install is running."""
        with self._lock:
            return self._process is not None

    def start(self, workspace: Path, agents: Sequence[str]) -> dict[str, Any]:
        """Start installing the hooks of some agents into a workspace.

        Args:
            workspace: The workspace directory.
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
                # encode every workspace path the installer prints.
                process = self._launch(
                    [
                        sys.executable,
                        "-u",
                        "-X",
                        "utf8",
                        "-m",
                        "vauxhall.hooks.cli",
                        *agents,
                    ],
                    cwd=workspace,
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
