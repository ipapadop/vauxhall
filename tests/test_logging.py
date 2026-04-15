# SPDX-License-Identifier: MIT

"""Tests for the logging configuration module."""

import logging

from vauxhall.logging_config import get_logger, setup_logging


def test_get_logger() -> None:
    """Verify that get_logger returns a logging.Logger instance."""
    logger = get_logger("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_setup_logging() -> None:
    """Verify that setup_logging can be called without error."""
    # Basic smoke test for setup_logging
    setup_logging(level=logging.DEBUG)
    # Check if root logger level is set (logging.basicConfig sets root logger)
    assert logging.getLogger().level == logging.DEBUG
