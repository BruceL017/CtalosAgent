"""
Structured Logger: 全链路结构化日志
每个日志带 task_id, session_id, tool_call_id, trace_id
支持 JSON 格式输出，便于 ELK/Loki 收集
"""
import json
import logging
import os
import sys
import time
import uuid
from typing import Any

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class StructuredLogFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + f"{record.msecs:03.0f}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add structured fields if present
        for key in ["task_id", "session_id", "tool_call_id", "trace_id", "provider", "error_type", "duration_ms"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


def get_structured_logger(name: str) -> logging.Logger:
    """Get a logger with structured JSON formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
        logger.propagate = False
    return logger


class ContextLogger:
    """Context-aware logger that carries trace context across calls."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ):
        self._logger = logger or get_structured_logger("agent.runtime")
        self.task_id = task_id
        self.session_id = session_id
        self.trace_id = trace_id or str(uuid.uuid4())

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        extra: dict[str, Any] = {"extra": dict(kwargs)}
        if self.task_id:
            extra["task_id"] = self.task_id
        if self.session_id:
            extra["session_id"] = self.session_id
        if self.trace_id:
            extra["trace_id"] = self.trace_id

        # Merge any additional context fields
        for key in ["tool_call_id", "provider", "error_type", "duration_ms"]:
            if key in kwargs:
                extra[key] = kwargs.pop(key)
                extra["extra"][key] = extra[key]

        record = self._logger.makeRecord(
            self._logger.name,
            level,
            "(unknown file)",
            0,
            message,
            (),
            None,
        )
        for key, val in extra.items():
            setattr(record, key, val)
        self._logger.handle(record)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def with_context(self, task_id: str | None = None, session_id: str | None = None, tool_call_id: str | None = None) -> "ContextLogger":
        """Create a new logger with additional context."""
        return ContextLogger(
            logger=self._logger,
            task_id=task_id or self.task_id,
            session_id=session_id or self.session_id,
            trace_id=self.trace_id,
        )
