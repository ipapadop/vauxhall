# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Centralized logging configuration for Vauxhall with color support."""

import logging
import sys
from typing import ClassVar

# C0 controls except tab and newline, DEL, and C1 controls, which a terminal
# would act on: an escape sequence from a topic or a path could rewrite the
# log line or the terminal's state.
_CONTROL_ESCAPES = {
    code: f"\\x{code:02x}"
    for code in (*range(0x09), *range(0x0B, 0x20), *range(0x7F, 0xA0))
}


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

    COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: BLUE,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }
    # One formatter per color, built once and reused for every record instead
    # of compiling a new format string on every call. A plain loop, not a
    # comprehension, since a comprehension's body can't see RESET from the
    # enclosing class scope.
    _FORMATTERS: ClassVar[dict[str, logging.Formatter]] = {}
    for _color in {*COLORS.values(), GREY}:
        _FORMATTERS[_color] = logging.Formatter(
            f"%(asctime)s [{_color}%(levelname)s{RESET}] %(name)s: %(message)s"
        )
    del _color  # pyright: ignore[reportPossiblyUnboundVariable]

    def format(self, record: logging.LogRecord) -> str:
        r"""Format a log record with a colored level name.

        Args:
            record: The log record to render.

        Returns:
            The formatted line, with the level name wrapped in color codes
            and control characters in the message, traceback, and stack
            shown as ``\xNN``.
        """
        exception = record.exc_text
        if record.exc_info:
            exception = self.formatException(record.exc_info)
        record = logging.makeLogRecord(
            {
                **record.__dict__,
                "msg": record.getMessage().translate(_CONTROL_ESCAPES),
                "args": None,
                "exc_info": None,
                "exc_text": exception and exception.translate(_CONTROL_ESCAPES),
                "stack_info": record.stack_info
                and record.stack_info.translate(_CONTROL_ESCAPES),
            }
        )
        formatter = self._FORMATTERS[self.COLORS.get(record.levelno, self.GREY)]
        return formatter.format(record)


class _LoggingState:
    """Internal state to track logging configuration."""

    setup_done: bool = False


def setup_logging(level: int | str = logging.INFO) -> None:
    """Configure colored root logging once per process.

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
