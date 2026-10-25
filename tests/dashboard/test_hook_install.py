# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for running the hook installer from the dashboard."""

import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

from tests.dashboard.fake_installer import WAIT_SECONDS, FakeProcess, Launcher
from vauxhall.dashboard.hook_install import ALREADY_RUNNING, HookInstallRunner


class Posted:
    """Collects posted window events and signals the end of an install."""

    def __init__(self) -> None:
        """Start with no events."""
        self.events: list[tuple[str, object]] = []
        self.done = threading.Event()

    def __call__(self, name: str, data: object) -> None:
        """Record an event.

        Args:
            name: The event name.
            data: The payload.
        """
        self.events.append((name, data))
        if name == "install-done":
            self.done.set()

    def wait(self) -> list[tuple[str, object]]:
        """Wait for ``install-done`` and return every event.

        Returns:
            The events posted so far.
        """
        assert self.done.wait(WAIT_SECONDS)
        return self.events


def _runner(*processes: FakeProcess) -> tuple[HookInstallRunner, Launcher, Posted]:
    """Build a runner over scripted processes.

    Args:
        processes: Processes the launcher returns in order.

    Returns:
        The runner, its launcher, and its event collector.
    """
    launcher = Launcher(*processes)
    posted = Posted()
    return HookInstallRunner(posted, launch=launcher), launcher, posted


def test_start_runs_the_installer_cli(tmp_path: Path) -> None:
    """The child runs the CLI unbuffered, in UTF-8 mode, with merged text output.

    Without UTF-8 mode a Windows child writes its pipe in the ANSI code page,
    and printing a workspace path outside it fails.
    """
    runner, launcher, posted = _runner(FakeProcess())

    assert runner.start(tmp_path, ["claude", "gemini"]) == {"ok": True}
    posted.wait()

    args, kwargs = launcher.launches[0]
    assert args == [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        "-m",
        "vauxhall.hooks.cli",
        "claude",
        "gemini",
    ]
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.STDOUT
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


def test_start_passes_the_workspace_as_cwd(tmp_path: Path) -> None:
    """The workspace is the child's directory, never part of a shell command."""
    workspace = tmp_path / "my wörkspace"
    workspace.mkdir()
    runner, launcher, posted = _runner(FakeProcess())

    runner.start(workspace, ["codex"])
    posted.wait()

    _, kwargs = launcher.launches[0]
    assert kwargs["cwd"] == workspace
    assert "shell" not in kwargs


def test_output_lines_are_posted_in_order_then_done(tmp_path: Path) -> None:
    """Each line is posted without its newline, then the exit status."""
    runner, _, posted = _runner(FakeProcess(["a\n", "b�\n"]))

    runner.start(tmp_path, ["claude"])

    assert posted.wait() == [
        ("install-output", {"line": "a"}),
        ("install-output", {"line": "b�"}),
        ("install-done", {"ok": True, "returncode": 0}),
    ]


def test_nonzero_exit_reports_failure(tmp_path: Path) -> None:
    """A failed installer ends the install with its exit status."""
    runner, _, posted = _runner(FakeProcess(["Error: x\n"], returncode=1))

    runner.start(tmp_path, ["claude"])

    assert posted.wait()[-1] == ("install-done", {"ok": False, "returncode": 1})


def test_second_start_while_running_is_refused(tmp_path: Path) -> None:
    """Only one install runs at a time."""
    release = threading.Event()
    runner, launcher, posted = _runner(FakeProcess(release=release))

    runner.start(tmp_path, ["claude"])
    assert runner.running is True
    assert runner.start(tmp_path, ["codex"]) == {
        "ok": False,
        "error": ALREADY_RUNNING,
    }
    release.set()
    posted.wait()

    assert len(launcher.launches) == 1
    assert runner.running is False


def test_start_after_done_runs_again(tmp_path: Path) -> None:
    """A finished install frees the runner for the next directory."""
    runner, launcher, posted = _runner(FakeProcess(), FakeProcess())

    runner.start(tmp_path, ["claude"])
    posted.wait()
    posted.done.clear()

    assert runner.start(tmp_path, ["codex"]) == {"ok": True}
    posted.wait()
    assert len(launcher.launches) == 2


def test_launch_oserror_is_returned(tmp_path: Path) -> None:
    """A child that can't start is reported without any events."""
    posted = Posted()
    runner = HookInstallRunner(posted, launch=Launcher(error=OSError("boom")))

    assert runner.start(tmp_path, ["claude"]) == {"ok": False, "error": "boom"}
    assert posted.events == []
    assert runner.running is False


def test_reader_exception_still_posts_done(tmp_path: Path) -> None:
    """A failure while reading output still unlocks the dialog."""

    def broken() -> Iterator[str]:
        yield "a\n"
        msg = "unreadable"
        raise ValueError(msg)

    process = FakeProcess()
    process.stdout = broken()
    runner, _, posted = _runner(process)

    runner.start(tmp_path, ["claude"])

    assert posted.wait()[-1] == ("install-done", {"ok": False, "returncode": None})
    assert runner.running is False


def test_close_terminates_then_kills(tmp_path: Path) -> None:
    """Shutdown stops a running install, killing one that won't exit."""
    release = threading.Event()
    process = FakeProcess(release=release, wait_timeouts=1)
    runner, _, posted = _runner(process)
    runner.start(tmp_path, ["claude"])

    runner.close(0.01)

    assert process.calls[:3] == ["terminate", "wait", "kill"]
    release.set()
    posted.wait()


def test_close_without_install_does_nothing() -> None:
    """Closing an idle runner has nothing to stop."""
    runner, launcher, _ = _runner()

    runner.close(0.01)

    assert launcher.launches == []
