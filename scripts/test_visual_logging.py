# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

from vauxhall.core.logging import get_logger, setup_logging


def test_visual_colors() -> None:
    """Visually test the color output of the logger."""
    setup_logging(level="DEBUG")
    logger = get_logger("test_color")
    logger.debug("This should be BLUE")
    logger.info("This should be GREEN")
    logger.warning("This should be YELLOW")
    logger.error("This should be RED")
    logger.critical("This should be BOLD RED")


if __name__ == "__main__":
    test_visual_colors()
