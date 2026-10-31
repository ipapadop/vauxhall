# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the dashboard entry point."""

import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from vauxhall.dashboard.main import (
    INSTANCE_LOCK_FILE,
    UI_DIR,
    _lock_dashboard,
    _serve_ui,
)


def test_dashboard_main_initializes_configured_logging(free_port: int) -> None:
    """The dashboard entry point must initialize logging before it runs.

    Args:
        free_port: A free port for the UI server.
    """
    code = """
import logging
from unittest.mock import patch

import vauxhall.core.logging
import vauxhall.dashboard.main

root = logging.getLogger()
root.handlers = [logging.NullHandler()]
root.setLevel(logging.CRITICAL)
vauxhall.core.logging._LoggingState.setup_done = False

with patch.object(vauxhall.dashboard.main.DashboardApp, "run"):
    vauxhall.dashboard.main.main()

print(root.level == logging.INFO and type(root.handlers[0]) is logging.StreamHandler)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "VAUXHALL_DASHBOARD_PORT": str(free_port),
        },
    )

    assert result.stdout.splitlines()[-1] == "True"


def test_dashboard_main_sets_safe_chromium_flags_and_keeps_the_users() -> None:
    """Pyloid's flags lose the certificate overrides; the user's follow them."""
    code = """
import os

import vauxhall.dashboard.main

print("after import:", os.environ["QTWEBENGINE_CHROMIUM_FLAGS"])

def stop(*_, **__):
    print("at startup:", os.environ["QTWEBENGINE_CHROMIUM_FLAGS"])
    raise SystemExit(0)

vauxhall.dashboard.main.Pyloid = stop
vauxhall.dashboard.main.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox"},
    )

    flags = {
        label: value
        for label, _, value in (
            line.partition(": ") for line in result.stdout.splitlines()
        )
        if label in {"after import", "at startup"}
    }
    insecure = {"--ignore-certificate-errors", "--allow-insecure-localhost"}
    assert insecure <= set(flags["after import"].split())
    assert flags["at startup"].split() == [
        *(flag for flag in flags["after import"].split() if flag not in insecure),
        "--disable-gpu",
        "--no-sandbox",
    ]


@pytest.mark.parametrize(
    ("backend", "expected_rhi", "expected_last_flag"),
    [("opengl", "opengl", "--no-sandbox"), ("software", "", "--disable-gpu")],
)
def test_dashboard_main_applies_the_graphics_backend(
    backend: str, expected_rhi: str, expected_last_flag: str
) -> None:
    """``main`` applies the configured graphics backend before creating Pyloid.

    Args:
        backend: The configured graphics backend.
        expected_rhi: The ``QSG_RHI_BACKEND`` Qt sees, empty when unset.
        expected_last_flag: The last Chromium flag Qt sees.
    """
    code = """
import os

import vauxhall.dashboard.main

def stop(*_, **__):
    print("rhi:", os.environ.get("QSG_RHI_BACKEND", ""))
    print("flags:", os.environ["QTWEBENGINE_CHROMIUM_FLAGS"])
    raise SystemExit(0)

vauxhall.dashboard.main.Pyloid = stop
vauxhall.dashboard.main.main()
"""
    env = {
        **os.environ,
        "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
        "VAUXHALL_DASHBOARD_GRAPHICS_BACKEND": backend,
    }
    env.pop("QSG_RHI_BACKEND", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )

    lines = dict(
        line.partition(": ")[::2]
        for line in result.stdout.splitlines()
        if line.startswith(("rhi:", "flags:"))
    )
    assert lines["rhi"] == expected_rhi
    assert lines["flags"].split()[-1] == expected_last_flag


def test_dashboard_main_refuses_to_run_beside_another_dashboard(
    isolated_home: Path,
) -> None:
    """A second dashboard exits before starting, naming the lock to delete.

    Args:
        isolated_home: The temporary home the dashboard locks under.
    """
    code = """
import vauxhall.dashboard.main

def stop(*_, **__):
    print("started")
    raise SystemExit(0)

vauxhall.dashboard.main.Pyloid = stop
vauxhall.dashboard.main.main()
"""
    path = isolated_home / ".config" / "vauxhall" / INSTANCE_LOCK_FILE
    lock = _lock_dashboard(path)
    try:
        refused = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
    finally:
        lock.unlock()
    started = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert refused.returncode == 1
    assert "started" not in refused.stdout
    assert "Another Vauxhall Dashboard is already running" in refused.stdout
    assert str(path) in refused.stdout
    assert "started" in started.stdout
    assert not path.exists()


def test_lock_dashboard_takes_over_a_lock_left_by_an_exited_process(
    tmp_path: Path,
) -> None:
    """A lock naming a process that no longer runs doesn't block startup.

    Args:
        tmp_path: Pytest temporary directory.
    """
    code = """
import os, sys
from PySide6.QtCore import QLockFile

lock = QLockFile(sys.argv[1])
assert lock.tryLock(0)
os._exit(0)
"""
    path = tmp_path / INSTANCE_LOCK_FILE
    subprocess.run([sys.executable, "-c", code, str(path)], check=True)
    assert path.exists()

    lock = _lock_dashboard(path)

    assert lock.isLocked()
    lock.unlock()


def test_lock_dashboard_runs_unlocked_when_the_lock_cant_be_created(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An unusable lock path is logged instead of stopping the dashboard.

    Args:
        tmp_path: Pytest temporary directory.
        caplog: Captures the warning.
    """
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")

    lock = _lock_dashboard(blocker / INSTANCE_LOCK_FILE)

    assert not lock.isLocked()
    assert "a second dashboard would not be refused" in caplog.text


def test_serve_ui_serves_the_shipped_page() -> None:
    """The server's URL loads the packaged index.html."""
    server = _serve_ui(0)
    try:
        port = urlsplit(server.url).port
        url = f"http://127.0.0.1:{port}/index.html"
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read()
    finally:
        server.close(1.0)

    assert body == (UI_DIR / "index.html").read_bytes()


def test_serve_ui_exits_when_another_program_holds_the_port(
    listening_port: int, caplog: pytest.LogCaptureFixture
) -> None:
    """A taken port stops startup instead of loading that program's page.

    Args:
        listening_port: A port another socket listens on.
        caplog: Captures the error.
    """
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exited:
        _serve_ui(listening_port)

    assert exited.value.code == 1
    assert f"127.0.0.1:{listening_port}" in caplog.text
    assert "dashboard.port" in caplog.text
