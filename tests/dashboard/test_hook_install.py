# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for running the hook installer from the dashboard."""

import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.dashboard.fake_installer import WAIT_SECONDS, FakeProcess, Launcher
from vauxhall.dashboard.hook_install import ALREADY_RUNNING, HookInstallRunner
from vauxhall.dashboard.ui_state import load_ui_state, update_ui_state


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
    runner = HookInstallRunner(posted, select_directory=MagicMock(), launch=launcher)
    return runner, launcher, posted


def test_start_runs_the_installer_cli(tmp_path: Path) -> None:
    """The child runs the CLI unbuffered, in UTF-8 mode, with merged text output.

    Without UTF-8 mode a Windows child writes its pipe in the ANSI code page,
    and printing a workspace path outside it fails. The workspace is the
    child's directory, never part of a shell command.
    """
    workspace = tmp_path / "my wörkspace"
    workspace.mkdir()
    runner, launcher, posted = _runner(FakeProcess())

    assert runner.install_hooks(workspace, ["claude", "gemini"]) == {"ok": True}
    posted.wait()

    args, kwargs = launcher.launches[0]
    assert args == [
        sys.executable,
        "-P",
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
    assert kwargs["cwd"] == workspace
    assert "shell" not in kwargs


def test_output_lines_are_posted_in_order_then_done(tmp_path: Path) -> None:
    """Each line is posted without its newline, then the exit status."""
    runner, _, posted = _runner(FakeProcess(["a\n", "b�\n"]))

    runner.install_hooks(tmp_path, ["claude"])

    assert posted.wait() == [
        ("install-output", {"line": "a"}),
        ("install-output", {"line": "b�"}),
        ("install-done", {"ok": True, "returncode": 0}),
    ]


def test_nonzero_exit_reports_failure(tmp_path: Path) -> None:
    """A failed installer ends the install with its exit status."""
    runner, _, posted = _runner(FakeProcess(["Error: x\n"], returncode=1))

    runner.install_hooks(tmp_path, ["claude"])

    assert posted.wait()[-1] == ("install-done", {"ok": False, "returncode": 1})


def test_one_install_runs_at_a_time(tmp_path: Path) -> None:
    """A second start is refused while one runs, and accepted once it ends."""
    release = threading.Event()
    runner, launcher, posted = _runner(FakeProcess(release=release), FakeProcess())

    runner.install_hooks(tmp_path, ["claude"])
    assert runner.running is True
    assert runner.install_hooks(tmp_path, ["codex"]) == {
        "ok": False,
        "error": ALREADY_RUNNING,
    }
    release.set()
    posted.wait()
    assert len(launcher.launches) == 1
    assert runner.running is False

    posted.done.clear()
    assert runner.install_hooks(tmp_path, ["codex"]) == {"ok": True}
    posted.wait()
    assert len(launcher.launches) == 2


def test_launch_oserror_is_returned(tmp_path: Path) -> None:
    """A child that can't start is reported without any events."""
    posted = Posted()
    runner = HookInstallRunner(
        posted, select_directory=MagicMock(), launch=Launcher(error=OSError("boom"))
    )

    assert runner.install_hooks(tmp_path, ["claude"]) == {"ok": False, "error": "boom"}
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

    runner.install_hooks(tmp_path, ["claude"])

    assert posted.wait()[-1] == ("install-done", {"ok": False, "returncode": None})
    assert runner.running is False


def test_close_terminates_then_kills(tmp_path: Path) -> None:
    """Shutdown stops a running install, killing one that won't exit."""
    release = threading.Event()
    process = FakeProcess(release=release, wait_timeouts=1)
    runner, _, posted = _runner(process)
    runner.install_hooks(tmp_path, ["claude"])

    runner.close(0.01)

    assert process.calls[:3] == ["terminate", "wait", "kill"]
    release.set()
    posted.wait()


def test_close_without_install_does_nothing() -> None:
    """Closing an idle runner has nothing to stop."""
    runner, launcher, _ = _runner()

    runner.close(0.01)

    assert launcher.launches == []


def test_the_workspace_cannot_replace_the_installer(tmp_path: Path) -> None:
    """A workspace's own vauxhall package or metadata is never imported.

    ``-m`` would put the child's working directory first on ``sys.path``, so
    a repository's ``vauxhall.egg-info`` hid the install's ``direct_url.json``
    (pinning the hooks to PyPI) and its ``vauxhall`` package would run.
    """
    decoy = tmp_path / "vauxhall" / "hooks"
    decoy.mkdir(parents=True)
    (tmp_path / "vauxhall" / "__init__.py").write_text("")
    (decoy / "__init__.py").write_text("")
    (decoy / "cli.py").write_text("print('decoy')\n")
    posted = Posted()

    HookInstallRunner(posted, select_directory=MagicMock()).install_hooks(
        tmp_path, ["--help"]
    )

    lines = [data["line"] for name, data in posted.wait() if name == "install-output"]
    assert "decoy" not in lines
    assert any("vauxhall-hook-install" in line for line in lines)


def _picker(choice: str | None) -> tuple[HookInstallRunner, MagicMock]:
    """Build a runner whose directory picker returns a fixed choice.

    Args:
        choice: The directory the picker returns, or ``None`` for cancel.

    Returns:
        The runner and its picker.
    """
    dialog = MagicMock(return_value=choice)
    return HookInstallRunner(MagicMock(), select_directory=dialog), dialog


def test_select_install_directory_opens_at_the_saved_directory(
    tmp_path: Path,
) -> None:
    """The picker starts where hooks were last installed; cancelling changes nothing."""
    update_ui_state({"install_directory": str(tmp_path)})
    runner, dialog = _picker(None)

    assert runner.select_install_directory() == {"ok": False}

    dialog.assert_called_once_with(dir=str(tmp_path))
    assert load_ui_state()["install_directory"] == str(tmp_path)


def test_select_install_directory_falls_back_to_home(tmp_path: Path) -> None:
    """A remembered directory that is gone opens the picker at home."""
    update_ui_state({"install_directory": str(tmp_path / "gone")})
    runner, dialog = _picker(None)

    runner.select_install_directory()

    dialog.assert_called_once_with(dir=str(Path.home()))


def test_select_install_directory_saves_and_detects(tmp_path: Path) -> None:
    """A chosen directory is remembered and its agents detected."""
    (tmp_path / ".claude").mkdir()
    runner, _ = _picker(str(tmp_path))

    result = runner.select_install_directory()

    assert result["ok"] is True
    assert result["path"] == str(tmp_path)
    assert [entry["detected"] for entry in result["agents"]] == [True, False, False]
    assert load_ui_state()["install_directory"] == str(tmp_path)


def test_select_install_directory_survives_a_failed_save(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Not remembering the directory doesn't stop the install."""
    runner, _ = _picker(str(tmp_path))

    with patch(
        "vauxhall.dashboard.hook_install.update_ui_state",
        side_effect=OSError("read-only"),
    ):
        result = runner.select_install_directory()

    assert result["ok"] is True
    assert "Could not remember the install directory" in caplog.text


def test_select_install_directory_skips_an_unreadable_saved_directory(
    unsearchable_dir: Path,
) -> None:
    """A remembered directory that can't be checked opens the picker at home."""
    update_ui_state({"install_directory": str(unsearchable_dir)})
    runner, dialog = _picker(None)

    runner.select_install_directory()

    dialog.assert_called_once_with(dir=str(Path.home()))
