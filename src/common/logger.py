import hashlib
import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra fields passed via `extra={}`
        for key in ("correlation_id", "phone_hash", "lambda_name", "session_id", "error"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def get_logger(name: str) -> logging.Logger:
    """Get a structured JSON logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def hash_phone(phone_number: str) -> str:
    """Hash phone number for safe logging. Never log raw phone numbers."""
    return hashlib.sha256(phone_number.encode()).hexdigest()[:12]


def log_context(**kwargs: Any) -> dict[str, Any]:
    """Build extra dict for structured logging."""
    return {k: v for k, v in kwargs.items() if v is not None}
