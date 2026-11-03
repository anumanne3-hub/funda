import json
import logging
import sys

from app.core.logging import JsonFormatter


def test_exception_diagnostics_exclude_sensitive_message():
    try:
        raise RuntimeError("private SQL parameter")
    except RuntimeError:
        record = logging.LogRecord(
            "app", logging.ERROR, __file__, 1, "request failed", (), sys.exc_info()
        )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["error_type"] == "RuntimeError"
    assert payload["traceback"][-1]["function"] == (
        "test_exception_diagnostics_exclude_sensitive_message"
    )
    assert "private SQL parameter" not in json.dumps(payload)
