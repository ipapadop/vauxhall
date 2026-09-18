# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests that importing dashboard config leaves host logging untouched."""

import os
import subprocess
import sys


def test_importing_dashboard_config_preserves_host_logging() -> None:
    """Importing dashboard config must preserve application root handlers."""
    code = """
import logging

root = logging.getLogger()
handler = logging.NullHandler()
root.handlers = [handler]

import vauxhall.dashboard.config

print(root.handlers == [handler])
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert result.stdout.strip() == "True"


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
