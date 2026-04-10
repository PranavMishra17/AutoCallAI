"""
Plan:
- Provide a single, reusable logger format for all scripts.
- Emit logs to stdout with the required [TIMESTAMP] [LEVEL] [COMPONENT] shape.
- Expose helpers for component-scoped loggers and safe payload truncation.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_FORMAT = "[%(asctime)s] [%(levelname)s] [%(component)s] %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


class _ComponentFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "component"):
            record.component = "core"
        return True


def _configure_root_logger() -> logging.Logger:
    logger = logging.getLogger("autocallai")
    if logger.handlers:
        return logger

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(_ComponentFilter())
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATEFMT))
    logger.addHandler(handler)
    return logger


def get_logger(component: str) -> logging.LoggerAdapter:
    base = _configure_root_logger()
    return logging.LoggerAdapter(base, {"component": component})


def truncate_text(value: Any, limit: int = 200) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."
