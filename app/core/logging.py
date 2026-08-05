import logging

from app.core.config import settings
from app.core.correlation import CorrelationIdLogFilter


def configure_logging() -> None:
    """Configure application-wide logging with a per-request correlation ID."""

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdLogFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | correlation_id=%(correlation_id)s"
            " | %(message)s"
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    root_logger.handlers = [handler]
