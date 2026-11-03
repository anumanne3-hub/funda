import json
import logging
import traceback
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Small JSON formatter for searchable logs without external dependencies."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "event", "conversation_id"):
            if value := getattr(record, key, None):
                payload[key] = value
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            payload["error_type"] = type(error).__name__
            # Exception messages can contain SQL parameters, credentials, or user text.
            payload["traceback"] = [
                {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(record.exc_info[2])
            ]
            original = getattr(error, "orig", error)
            if sqlstate := getattr(original, "sqlstate", None):
                payload["sqlstate"] = sqlstate
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
