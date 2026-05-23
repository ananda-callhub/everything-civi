"""Structured JSON logging configuration for everything-civi."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields passed via logger.info("msg", extra={...})
        # Exclude standard LogRecord attributes to get only user-supplied extras.
        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "pathname",
            "filename", "module", "thread", "threadName", "process",
            "processName", "levelname", "levelno", "message", "msecs",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_entry[key] = value

        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the everything_civi logger with JSON output to stdout.

    Uses a named logger to avoid clobbering handlers set by other libraries.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    pkg_logger = logging.getLogger("everything_civi")
    pkg_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    pkg_logger.handlers.clear()
    pkg_logger.addHandler(handler)
    pkg_logger.propagate = False
