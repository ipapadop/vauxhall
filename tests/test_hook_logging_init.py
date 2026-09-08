# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for logging behavior when Vauxhall is imported as a library."""

import subprocess
import sys


def test_importing_telemetry_client_preserves_host_logging() -> None:
    """Importing the client must not replace an application's root handlers."""
    code = """
import logging

root = logging.getLogger()
handler = logging.NullHandler()
root.handlers = [handler]

import vauxhall.hooks.client

print(root.handlers == [handler])
"""

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "True"
