"""Logging setup for AI for Breakfast automation."""

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import BASE_DIR

LOG_PATH = os.path.join(BASE_DIR, "app.log")


def setup_logging():
    """Configure logging to stdout and rotating file."""
    logger = logging.getLogger("ai4breakfast")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Stdout
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # Rotating file (5MB, keep 3)
    fh = RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = setup_logging()
