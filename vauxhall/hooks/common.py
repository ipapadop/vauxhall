# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Helpers shared by the built-in Codex and Gemini hooks and installers."""

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from vauxhall import __version__
from vauxhall.core.config import ConfigurationError

WINDOWS_ENCODED_COMMAND_PREFIX = (
    "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
)
_CANCELLATION_MARKERS = frozenset({"cancelled", "canceled", "aborted"})


def is_cancelled(response: dict[str, Any]) -> bool:
    """Return whether a tool response contains a cancellation marker."""
    if response.get("cancelled") is True or response.get("canceled") is True:
        return True
    candidates = [response.get(key) for key in ("code", "status", "name")]
    error = response.get("error")
    if isinstance(error, dict):
        candidates.extend(error.get(key) for key in ("code", "status", "name"))
    return any(
        isinstance(value, str) and value.lower() in _CANCELLATION_MARKERS
        for value in candidates
    )


def run_hook(send_telemetry: Callable[[dict[str, Any]], None]) -> None:
    """Process one hook event from stdin without disrupting the hook protocol."""
    try:
        with redirect_stdout(sys.stderr):
            from vauxhall.core.logging import setup_logging  # noqa: PLC0415
            from vauxhall.hooks.config import hook_settings  # noqa: PLC0415

            setup_logging(level=hook_settings.logging.level)
            input_data = json.load(sys.stdin)
            if isinstance(input_data, dict):
                send_telemetry(input_data)
    except ConfigurationError as error:
        print(error, file=sys.stderr)
    except Exception:
        pass
    print("{}")


def build_hook_command(venv_python: Path, module: str) -> str:
    """Build a platform-appropriate command that runs a hook module."""
    if os.name == "nt":
        python_path = str(venv_python).replace("'", "''")
        script = f"& '{python_path}' -m {module}"
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode()
        return f"{WINDOWS_ENCODED_COMMAND_PREFIX}{encoded_script}"
    return shlex.join([str(venv_python), "-m", module])


def setup_venv(venv_dir: Path) -> Path:
    """Create an isolated environment containing the Vauxhall hooks package.

    Args:
        venv_dir: Destination for the virtual environment.

    Returns:
        Path to the environment's Python executable.
    """
    if venv_dir.exists():
        print(f"Removing existing venv at {venv_dir}...")
        shutil.rmtree(venv_dir)

    print(f"Creating virtual environment in {venv_dir}...")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    requirement = f"vauxhall[hooks]=={__version__}"
    print(f"Installing {requirement}...")
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", requirement],
        check=True,
        capture_output=True,
    )
    return venv_python
