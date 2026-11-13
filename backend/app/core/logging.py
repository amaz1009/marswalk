"""Logging setup for MARSWALK backend."""

import logging
import sys

from app.config import get_settings


def setup_logging() -> None:
    """Configure root logger with log level from settings."""
    settings = get_settings()
    log_level = getattr(logging, settings.MARSWALK_LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


logger = logging.getLogger("marswalk")
