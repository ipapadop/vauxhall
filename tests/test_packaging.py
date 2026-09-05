# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the installable package artifact."""

import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_contains_dashboard_ui(tmp_path: Path) -> None:
    """Ensure dashboard installations include every frontend asset."""
    project_root = Path(__file__).parents[1]
    wheel_dir = tmp_path / "wheel"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheel_dir),
            str(project_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_path = next(wheel_dir.glob("*.whl"))
    with zipfile.ZipFile(wheel_path) as wheel:
        packaged_files = set(wheel.namelist())

    assert {
        "vauxhall/dashboard/ui/app.js",
        "vauxhall/dashboard/ui/icon.png",
        "vauxhall/dashboard/ui/index.html",
        "vauxhall/dashboard/ui/js/ipc.js",
        "vauxhall/dashboard/ui/js/state.js",
        "vauxhall/dashboard/ui/js/ui.js",
        "vauxhall/dashboard/ui/logo.svg",
        "vauxhall/dashboard/ui/style.css",
    } <= packaged_files
