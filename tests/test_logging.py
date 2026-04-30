# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the logging configuration module."""

import logging

import vauxhall.core.logging
from vauxhall.core.logging import get_logger, setup_logging


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
