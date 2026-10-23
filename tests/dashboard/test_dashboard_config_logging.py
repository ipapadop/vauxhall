# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the dashboard entry point."""

import os
import subprocess
import sys


def test_dashboard_main_initializes_configured_logging() -> None:
    """The dashboard entry point must initialize logging before it runs."""
    code = """
import logging
from unittest.mock import patch

import vauxhall.core.logging
import vauxhall.dashboard.app

root = logging.getLogger()
root.handlers = [logging.NullHandler()]
root.setLevel(logging.CRITICAL)
vauxhall.core.logging._LoggingState.setup_done = False

with patch.object(vauxhall.dashboard.app.DashboardApp, "run"):
    vauxhall.dashboard.app.main()

print(root.level == logging.INFO and type(root.handlers[0]) is logging.StreamHandler)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

    assert result.stdout.splitlines()[-1] == "True"


def test_dashboard_main_sets_safe_chromium_flags_and_keeps_the_users() -> None:
    """Pyloid's flags lose the certificate overrides; the user's follow them."""
    code = """
import os

import vauxhall.dashboard.app

print("after import:", os.environ["QTWEBENGINE_CHROMIUM_FLAGS"])

def stop(*_, **__):
    print("at startup:", os.environ["QTWEBENGINE_CHROMIUM_FLAGS"])
    raise SystemExit(0)

vauxhall.dashboard.app.Pyloid = stop
vauxhall.dashboard.app.main()
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
