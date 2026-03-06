from __future__ import annotations

import logging
import os
import sys

from loguru import logger

_CONFIGURED = False
_DEFAULT_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}"
)


class _InterceptHandler(logging.Handler):
    """Forward stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(exception=record.exc_info, depth=6).log(level, record.getMessage())


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging(level: str | None = None) -> None:
    """Configure loguru once for the whole process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    log_format = os.getenv("LOG_FORMAT", _DEFAULT_LOG_FORMAT)
    backtrace = _env_bool("LOG_BACKTRACE", default=False)
    diagnose = _env_bool("LOG_DIAGNOSE", default=False)
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format=log_format,
        backtrace=backtrace,
        diagnose=diagnose,
    )
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    _CONFIGURED = True
