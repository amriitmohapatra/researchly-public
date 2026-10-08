"""Structured JSON logs that cannot carry document text.

Non-negotiable #2 / ADR-02: document text is never logged. The rules here:

- **One line per request**, written by the request middleware with a fixed
  set of fields (request_id, route template, status, latency, content
  length, format, suggestion counts). Never the body, the query string, the
  raw path, a suggestion's `text`, or an exception message.
- **Exceptions are logged by type and code location only.** An exception's
  message is data-dependent (a spaCy or LanguageTool error can quote its
  input), and so are frame locals. The formatter therefore NEVER renders
  `exc_info` the normal way — any record carrying an exception, from any
  logger including uvicorn's, is reduced to the exception class name and
  `file:line in function` frames, which are code, not data.
- **Python warnings** are reduced to their category: a warning's message can
  quote text (spaCy's alignment warnings do).
- **uvicorn's access log is off.** It prints the raw request line, which
  includes any query string a client chooses to send.

Output goes to stdout as one JSON object per line, with `severity` and
`message` keys so Cloud Logging parses it natively.

tests/test_privacy_canary.py (ARCHITECTURE.md Q6) is the evidence.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
import warnings

# Fields a log record may carry into the JSON line (set via `extra=`).
# Anything else attached to a record is dropped, so a careless
# `extra={"content": ...}` cannot reach the log.
ALLOWED_FIELDS = (
    "event", "request_id", "method", "route", "status", "latency_ms",
    "content_chars", "format", "suggestions", "counts", "hidden_preferences",
    "code", "error_type", "frames", "rules_loaded", "tiers", "grammar",
    "warmup_ms", "lt_url_set", "allowed_origins", "rate_limit_per_min",
    "service_version", "core_version", "category", "where",
    # S2. Never the filename, the token, the user id or any setting value.
    "upload_bytes", "signed_in", "accounts", "anon_max_words",
)

_SEVERITY = {"DEBUG": "DEBUG", "INFO": "INFO", "WARNING": "WARNING",
             "ERROR": "ERROR", "CRITICAL": "CRITICAL"}


def safe_frames(tb, limit: int = 12) -> list:
    """`file:line in function` for each frame — code locations, no data."""
    out = []
    try:
        for fs in traceback.extract_tb(tb)[-limit:]:
            out.append(f"{os.path.basename(fs.filename)}:{fs.lineno} "
                       f"in {fs.name}")
    except Exception:
        pass
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S",
                                time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "severity": _SEVERITY.get(record.levelname, "DEFAULT"),
            "logger": record.name,
        }
        if record.exc_info and record.exc_info[0] is not None:
            etype, _evalue, tb = record.exc_info
            # Only the class name and code locations. Never str(evalue),
            # never the formatted traceback (which repeats the message).
            line["message"] = "exception"
            line["error_type"] = etype.__name__
            line["frames"] = safe_frames(tb)
        else:
            line["message"] = self._message(record)
        for key in ALLOWED_FIELDS:
            if key in record.__dict__ and key not in line:
                line[key] = record.__dict__[key]
        return json.dumps(line, ensure_ascii=False, default=str)

    @staticmethod
    def _message(record: logging.LogRecord) -> str:
        # Our own loggers log fixed strings. Third-party records are
        # rendered normally (uvicorn's startup lines, etc.), since none of
        # them is handed request data on our code paths; exceptions — the
        # one route by which data reaches a message — are handled above.
        try:
            return record.getMessage()
        except Exception:
            return str(record.msg)


class StdoutJsonHandler(logging.StreamHandler):
    """JSON to whatever sys.stdout is at emit time, and silent on failure.

    The stock `Handler.handleError` prints "--- Logging error ---" with a
    traceback to stderr. Called while another exception is being handled,
    that traceback includes the chained original — whose message can quote
    the document (the Q6 canary suite caught exactly this with a closed
    stdout). A log line that cannot be written is dropped, never dumped.
    """

    def __init__(self, stream=None):
        super().__init__(stream)
        self._fixed = stream

    @property
    def stream(self):
        return self._fixed if self._fixed is not None else sys.stdout

    @stream.setter
    def stream(self, value):
        self._fixed = value

    def handleError(self, record):
        pass


def _showwarning(message, category, filename, lineno, file=None, line=None):
    logging.getLogger("researchly.warnings").warning(
        "python warning", extra={"event": "python_warning",
                                 "category": category.__name__,
                                 "where": f"{os.path.basename(filename)}:"
                                          f"{lineno}"})


_CONFIGURED = False


def setup(level: int = logging.INFO, stream=None) -> None:
    """Route every logger through one JSON handler. Idempotent."""
    global _CONFIGURED
    # Never print a logging failure's traceback (see StdoutJsonHandler); this
    # covers every handler, including ones a library adds later.
    logging.raiseExceptions = False
    handler = StdoutJsonHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.set_name("researchly-json")

    root = logging.getLogger()
    for h in list(root.handlers):
        if h.get_name() == "researchly-json":
            root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its own handlers when it configures logging; we start
    # it with log_config=None, and strip them here in case it did anyway.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.asgi"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True                       # raw request line: never

    # The LanguageTool client logs request URLs at DEBUG; keep it quiet.
    logging.getLogger("language_tool_python").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    warnings.showwarning = _showwarning
    _CONFIGURED = True


def get(name: str = "researchly.service") -> logging.Logger:
    return logging.getLogger(name)
