"""Structured logging setup for repo-cartographer."""

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """Configure root and application loggers."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    # Custom log format with timestamps and module names
    log_format = (
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s"
    )

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    # Suppress verbose noise from third-party libraries in debug mode
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)


logger = logging.getLogger("repo_cartographer")
