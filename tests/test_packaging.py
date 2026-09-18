# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the installable package artifact."""

import base64
import configparser
import importlib.metadata
import json
import os
import shlex
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest

import vauxhall


def _build_wheel(wheel_dir: Path) -> Path:
    """Build and return the project's wheel.

    Args:
        wheel_dir: Directory the wheel is built into.

    Returns:
        The path of the built wheel.
    """
    project_root = Path(__file__).parents[1]
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
    return next(wheel_dir.glob("*.whl"))


def _venv_python(venv_dir: Path) -> Path:
    """Return the Python executable for a virtual environment.

    Args:
        venv_dir: Root of the virtual environment.

    Returns:
        The path of the Python executable.
    """
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_script(venv_dir: Path, name: str) -> Path:
    """Return a console-script path for a virtual environment.

    Args:
        venv_dir: Root of the virtual environment.
        name: Name of the console script.

    Returns:
        The path of the console script.
    """
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def test_wheel_contains_runtime_files(tmp_path: Path) -> None:
    """Ensure installations include dashboard assets and agent hooks.

    Args:
        tmp_path: Pytest temporary directory.
    """
    wheel_dir = tmp_path / "wheel"
    wheel_path = _build_wheel(wheel_dir)
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
        "vauxhall/core/telemetry.py",
        "vauxhall/hooks/identity.py",
        "vauxhall/hooks/claude/__init__.py",
        "vauxhall/hooks/claude/install.py",
        "vauxhall/hooks/claude/telemetry_hook.py",
        "vauxhall/hooks/codex/__init__.py",
        "vauxhall/hooks/codex/install.py",
        "vauxhall/hooks/codex/messages.py",
        "vauxhall/hooks/codex/telemetry_hook.py",
    } <= packaged_files


def test_wheel_hook_client_imports_without_typing_self(tmp_path: Path) -> None:
    """The packaged hooks must import on runtimes where typing lacks Self.

    Args:
        tmp_path: Pytest temporary directory.
    """
    wheel_path = _build_wheel(tmp_path / "wheel")
    runtime_check = """
import builtins
import sys

sys.path.insert(0, sys.argv[1])
import paho.mqtt.client
import vauxhall

real_import = builtins.__import__


def python_310_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "typing" and "Self" in fromlist:
        raise ImportError("cannot import name 'Self' from 'typing'")
    return real_import(name, globals, locals, fromlist, level)


builtins.__import__ = python_310_import
import vauxhall.hooks.client as client

print(client.__file__)
"""

    result = subprocess.run(
        [sys.executable, "-c", runtime_check, str(wheel_path)],
        check=True,
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert str(wheel_path) in result.stdout


def test_wheel_and_sdist_pass_strict_twine_check(tmp_path: Path) -> None:
    """Both publication artifacts must pass Twine without warnings.

    Args:
        tmp_path: Pytest temporary directory.
    """
    project_root = Path(__file__).parents[1]
    dist_dir = tmp_path / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(dist_dir),
            str(project_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "twine",
            "check",
            "--strict",
            *[str(path) for path in sorted(dist_dir.iterdir())],
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_wheel_exposes_complete_package_metadata(tmp_path: Path) -> None:
    """Built distributions must expose publishable metadata and commands.

    Args:
        tmp_path: Pytest temporary directory.
    """
    wheel_path = _build_wheel(tmp_path / "wheel")

    with zipfile.ZipFile(wheel_path) as wheel:
        metadata_name = next(
            name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")
        )
        entry_points_name = next(
            name
            for name in wheel.namelist()
            if name.endswith(".dist-info/entry_points.txt")
        )
        metadata = Parser().parsestr(wheel.read(metadata_name).decode())
        entry_points = configparser.ConfigParser()
        entry_points.read_string(wheel.read(entry_points_name).decode())

    assert metadata["Description-Content-Type"] == "text/markdown"
    assert metadata["License-Expression"] == "MIT"
    assert metadata.get_all("License-File") == ["LICENSE"]
    assert metadata["Author-email"] == (
        "Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>"
    )
    assert metadata["Maintainer-email"] == (
        "Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>"
    )
    assert metadata["Keywords"] == (
        "ai-agents,dashboard,hooks,monitoring,mqtt,telemetry"
    )
    assert set(metadata.get_all("Project-URL")) == {
        "Repository, https://github.com/ipapadop/vauxhall",
        "Documentation, https://github.com/ipapadop/vauxhall#readme",
        "Issues, https://github.com/ipapadop/vauxhall/issues",
        "Changelog, https://github.com/ipapadop/vauxhall/releases",
        "Security, https://github.com/ipapadop/vauxhall/security/advisories",
    }
    assert {
        "Development Status :: 3 - Alpha",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    } <= set(metadata.get_all("Classifier"))
    assert entry_points["console_scripts"] == {
        "vauxhall": "vauxhall.dashboard.app:main",
        "vauxhall-hook-install": "vauxhall.hooks.cli:main",
    }
    assert 'pyloid>=0.27.2; extra == "dashboard"' in metadata.get_all("Requires-Dist")


def test_package_version_matches_installed_distribution() -> None:
    """The public package version must derive from distribution metadata."""
    assert vauxhall.__version__ == importlib.metadata.version("vauxhall")


@pytest.mark.parametrize(
    ("agent", "config_path", "hook_module"),
    [
        (
            "claude",
            Path(".claude/settings.local.json"),
            "vauxhall.hooks.claude.telemetry_hook",
        ),
        (
            "codex",
            Path(".codex/hooks.json"),
            "vauxhall.hooks.codex.telemetry_hook",
        ),
        (
            "gemini",
            Path(".gemini/settings.json"),
            "vauxhall.hooks.gemini.telemetry_hook",
        ),
    ],
)
def test_wheel_installer_is_independent_of_source_checkout(
    tmp_path: Path,
    agent: str,
    config_path: Path,
    hook_module: str,
) -> None:
    """The public installer must install and register only wheel-contained code.

    Args:
        tmp_path: Pytest temporary directory.
        agent: The case's agent.
        config_path: Path of the configuration file.
        hook_module: The hook module the case installs.
    """
    project_root = Path(__file__).parents[1]
    wheel_dir = tmp_path / "wheelhouse"
    wheel_path = _build_wheel(wheel_dir)
    installer_venv = tmp_path / "installer-venv"
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()

    subprocess.run(
        [sys.executable, "-m", "venv", str(installer_venv)],
        check=True,
        capture_output=True,
        text=True,
    )
    installer_python = _venv_python(installer_venv)
    subprocess.run(
        [
            str(installer_python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(wheel_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    installed_module = subprocess.run(
        [str(installer_python), "-c", "import vauxhall; print(vauxhall.__file__)"],
        check=True,
        capture_output=True,
        cwd=workspace,
        text=True,
    ).stdout.strip()
    assert str(project_root) not in installed_module

    environment = os.environ.copy()
    environment.update(
        {
            "PIP_FIND_LINKS": str(wheel_dir),
            "PIP_NO_DEPS": "1",
            "PIP_NO_INDEX": "1",
        }
    )
    subprocess.run(
        [str(_venv_script(installer_venv, "vauxhall-hook-install")), agent],
        check=True,
        capture_output=True,
        cwd=workspace,
        env=environment,
        text=True,
    )

    generated_config = json.loads((workspace / config_path).read_text())
    generated_text = json.dumps(generated_config)
    hook_python = _venv_python(workspace / ".vauxhall-venv").absolute()
    assert str(project_root) not in generated_text
    hook_commands = [
        hook["command"]
        for groups in generated_config["hooks"].values()
        for group in groups
        for hook in group["hooks"]
    ]
    assert hook_commands
    for hook_command in hook_commands:
        if os.name == "nt":
            encoded_script = hook_command.rsplit(" ", maxsplit=1)[1]
            script = base64.b64decode(encoded_script).decode("utf-16-le")
            python_path = str(hook_python).replace("'", "''")
            assert script == f"& '{python_path}' -m {hook_module}"
        else:
            assert shlex.split(hook_command) == [str(hook_python), "-m", hook_module]
    installed_version = subprocess.run(
        [
            str(hook_python),
            "-c",
            "import importlib.metadata; print(importlib.metadata.version('vauxhall'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert installed_version == "0.1.0"
