"""Logging configuration"""

import logging
import sys


def setup_logging(level: int = logging.INFO):
    """Setup logging"""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
