# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Centralized logging configuration for Vauxhall with color support."""

import logging
import sys
from typing import ClassVar


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add ANSI colors to log levels."""

    # ANSI escape sequences for colors
    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    GREEN = "\x1b[32;20m"
    RESET = "\x1b[0m"

    FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: BLUE,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors.

        Args:
            record: The log record to format.

        Returns:
            str: The formatted log record.
        """
        log_color = self.COLORS.get(record.levelno, self.GREY)
        format_str = (
            f"%(asctime)s [{log_color}%(levelname)s{self.RESET}] %(name)s: %(message)s"
        )
        formatter = logging.Formatter(format_str)
        return formatter.format(record)


class _LoggingState:
    """Internal state to track logging configuration."""

    setup_done: bool = False


def setup_logging(level: int | str = logging.INFO) -> None:
    """Set up the default logging configuration with color.

    Args:
        level: The logging level to use. Defaults to logging.INFO.
    """
    if _LoggingState.setup_done:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter())

    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,
    )
    _LoggingState.setup_done = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: The name of the logger.

    Returns:
        logging.Logger: The logger instance.
    """
    return logging.getLogger(name)
