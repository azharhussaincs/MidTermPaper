"""Structured logging configuration (named to avoid shadowing stdlib `logging`)."""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str | int = "INFO") -> None:
    """Configure root logging once; safe to call repeatedly."""
    root = logging.getLogger()
    if not any(getattr(h, "_app_handler", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        handler._app_handler = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level.upper() if isinstance(level, str) else level)
    # Keep third-party HTTP chatter out of our logs.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
