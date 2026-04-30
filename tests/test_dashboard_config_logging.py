# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

import subprocess
import sys


def test_dashboard_config_auto_initializes_logging() -> None:
    """Verify that importing vauxhall.dashboard.config initializes logging."""
    code = """
import vauxhall.core.logging
import vauxhall.dashboard.config
print(vauxhall.core.logging._LoggingState.setup_done)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "True"
