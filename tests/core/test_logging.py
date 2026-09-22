# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the logging configuration module."""

import logging

import pytest

import vauxhall.core.logging
from vauxhall.core.logging import ColoredFormatter, get_logger, setup_logging


def test_get_logger() -> None:
    """Verify that get_logger returns a logging.Logger instance."""
    logger = get_logger("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_setup_logging() -> None:
    """Verify that setup_logging can be called without error."""
    # Reset for test
    vauxhall.core.logging._LoggingState.setup_done = False

    # Basic smoke test for setup_logging
    setup_logging(level=logging.DEBUG)
    # Check if root logger level is set (logging.basicConfig sets root logger)
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_string_level() -> None:
    """Verify that setup_logging handles string levels."""
    # Reset for test
    vauxhall.core.logging._LoggingState.setup_done = False

    setup_logging(level="INFO")
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_idempotency() -> None:
    """Verify that setup_logging is idempotent."""
    # Reset for test
    vauxhall.core.logging._LoggingState.setup_done = False

    # First call
    setup_logging(level=logging.WARNING)
    initial_level = logging.getLogger().level

    # Second call with different level should be ignored if idempotent
    setup_logging(level=logging.ERROR)
    assert logging.getLogger().level == initial_level


def test_colored_formatter_wraps_level_name_in_its_color() -> None:
    """Verify each level's rendered line carries that level's color codes."""
    formatter = ColoredFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="boom",
        args=(),
        exc_info=None,
    )

    line = formatter.format(record)

    assert f"{ColoredFormatter.RED}ERROR{ColoredFormatter.RESET}" in line


def test_colored_formatter_does_not_build_a_formatter_per_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify format() reuses a cached Formatter instead of building one per call."""
    formatter = ColoredFormatter()
    original_init = logging.Formatter.__init__
    calls = []

    def spy_init(self: logging.Formatter, *args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        original_init(self, *args, **kwargs)

    # Construct the ColoredFormatter itself before patching: it calls
    # Formatter.__init__ once through inheritance, which format() need not avoid.
    monkeypatch.setattr(logging.Formatter, "__init__", spy_init)
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )

    formatter.format(record)
    formatter.format(record)

    assert calls == []
