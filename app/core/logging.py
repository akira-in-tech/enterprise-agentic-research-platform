import logging

from app.core.config import settings


def configure_logging() -> None:
    """Configure application-wide logging."""

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )