# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Scripted child processes standing in for the hook installer."""

import subprocess
import threading
from collections.abc import Iterable, Iterator
from typing import Any

WAIT_SECONDS = 5


class FakeProcess:
    """A child process whose output and exit are scripted."""

    def __init__(
        self,
        lines: Iterable[str] = (),
        returncode: int = 0,
        release: threading.Event | None = None,
        wait_timeouts: int = 0,
    ) -> None:
        """Script the process.

        Args:
            lines: Output lines, read until exhausted.
            returncode: Exit status ``wait`` returns.
            release: When set, output ends only once it is set.
            wait_timeouts: How many ``wait`` calls with a timeout raise
                ``TimeoutExpired`` first.
        """
        self.stdout = self._read(lines, release)
        self.returncode = returncode
        self.wait_timeouts = wait_timeouts
        self.calls: list[str] = []

    @staticmethod
    def _read(lines: Iterable[str], release: threading.Event | None) -> Iterator[str]:
        """Yield the scripted output.

        Args:
            lines: Output lines.
            release: Optional event that ends the output.

        Yields:
            Each line.
        """
        yield from lines
        if release is not None:
            release.wait(WAIT_SECONDS)

    def wait(self, timeout: float | None = None) -> int:
        """Return the exit status, or time out as scripted.

        Args:
            timeout: Seconds to wait, as ``Popen.wait`` takes.

        Returns:
            The scripted exit status.

        Raises:
            subprocess.TimeoutExpired: While scripted timeouts remain.
        """
        self.calls.append("wait")
        if timeout is not None and self.wait_timeouts:
            self.wait_timeouts -= 1
            command = "installer"
            raise subprocess.TimeoutExpired(command, timeout)
        return self.returncode

    def terminate(self) -> None:
        """Record termination."""
        self.calls.append("terminate")

    def kill(self) -> None:
        """Record killing."""
        self.calls.append("kill")


class Launcher:
    """Records launches and returns scripted processes."""

    def __init__(self, *processes: FakeProcess, error: OSError | None = None) -> None:
        """Script the launches.

        Args:
            processes: Processes returned in order.
            error: Raised by every launch instead, when given.
        """
        self.processes = list(processes)
        self.error = error
        self.launches: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> FakeProcess:  # noqa: ANN401
        """Record a launch.

        Args:
            args: The command line.
            **kwargs: The ``Popen`` options.

        Returns:
            The next scripted process.

        Raises:
            OSError: When scripted to fail.
        """
        self.launches.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.processes.pop(0)
