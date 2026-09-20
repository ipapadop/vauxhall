# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Command-line installer for the built-in agent telemetry hooks."""

import argparse
from collections.abc import Sequence

from vauxhall.hooks import installation
from vauxhall.hooks.claude import install as claude
from vauxhall.hooks.codex import install as codex
from vauxhall.hooks.gemini import install as gemini

INSTALLERS = {
    "claude": claude.INSTALLER,
    "codex": codex.INSTALLER,
    "gemini": gemini.INSTALLER,
}


def main(argv: Sequence[str] | None = None) -> None:
    """Install the hooks of every agent named on the command line.

    Args:
        argv: Arguments to parse, or ``None`` to read them from the command
            line.
    """
    parser = argparse.ArgumentParser(
        prog="vauxhall-hook-install",
        description=(
            "Install Vauxhall telemetry hooks into the current workspace. "
            "Agents installed together share one hooks environment."
        ),
    )
    parser.add_argument(
        "agents",
        nargs="+",
        choices=sorted(INSTALLERS),
        help="agent to install hooks for",
    )
    arguments = parser.parse_args(argv)
    # Naming an agent twice would install it twice into the same settings file.
    agents = dict.fromkeys(arguments.agents)
    installation.install_hooks([INSTALLERS[agent] for agent in agents])


if __name__ == "__main__":
    main()
