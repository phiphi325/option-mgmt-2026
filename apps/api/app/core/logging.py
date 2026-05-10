"""Structured logging setup.

Stdlib logging for now; Phase 2 may switch to loguru + JSON output for
shipping to Better Stack / Datadog (per plan §14 observability).
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Idempotent root-logger configuration."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. in tests)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
