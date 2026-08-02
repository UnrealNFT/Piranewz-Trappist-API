"""Centralised logging setup."""

import logging
import sys


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Return a configured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            )
        )
        logger.addHandler(handler)

    return logger
