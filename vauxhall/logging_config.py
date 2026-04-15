# SPDX-License-Identifier: MIT

"""Centralized logging configuration for Vauxhall."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Set up the default logging configuration.

    Args:
        level: The logging level to use. Defaults to logging.INFO.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: The name of the logger.

    Returns:
        logging.Logger: The logger instance.
    """
    return logging.getLogger(name)
