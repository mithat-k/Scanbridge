"""
logger.py

Centralised loguru-based logging for Scanbridge.

- Two daily-rotated log files inside logs/ (14 days retention):
    scanbridge_app_YYYY-MM-DD.log  – application / engine events (+ third-party libs)
    ui_engine_YYYY-MM-DD.log       – UI specific events
- Standard-library `logging` records (EasyOCR, Pix2Text, huggingface_hub …)
  are intercepted and routed into loguru.
- sys.stdout / sys.stderr are redirected into the log, line-buffered, so the
  app can run without a terminal (.pyw). Carriage-return progress bars
  (tqdm, EasyOCR) are collapsed: only their final state is written.
- Uncaught exceptions (main thread, threading, Qt slots) are logged with a
  full traceback; Qt's own warnings can be routed via install_qt_message_handler().

Environment variables:
    SCANBRIDGE_LOG_LEVEL    minimum level for the app log (default INFO)
    SCANBRIDGE_LOG_CONSOLE  "1" → also echo logs to the real console (dev aid)

Ready-to-import loggers:
    app_logger – general application / engine events
    ui_logger  – UI events (separate file)
"""

from __future__ import annotations

import inspect
import logging
import os
import sys
import threading

from loguru import logger

LOG_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_LEVEL = os.environ.get("SCANBRIDGE_LOG_LEVEL", "INFO").upper()
_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {thread.name: <12} | "
    "{name}:{function}:{line} | {message}"
)

# Third-party modules that are far too chatty at INFO level.
_NOISY_LIBS = ("PIL", "urllib3", "matplotlib", "filelock", "httpx", "httpcore", "fsspec")


def _is_ui(record) -> bool:
    return record["extra"].get("channel") == "ui"


def _configure_sinks() -> None:
    logger.remove()  # drop loguru's default stderr sink (no console at runtime)
    logger.configure(extra={"channel": "app"})

    common = dict(
        format=_FORMAT,
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        backtrace=True,
        # diagnose=True would dump local variable values (file paths, OCR
        # text) into tracebacks — keep document content out of the logs.
        diagnose=False,
    )
    logger.add(
        os.path.join(LOG_DIR, "scanbridge_app_{time:YYYY-MM-DD}.log"),
        level=_LEVEL,
        filter=lambda r: not _is_ui(r),
        **common,
    )
    logger.add(
        os.path.join(LOG_DIR, "ui_engine_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        filter=_is_ui,
        **common,
    )

    if os.environ.get("SCANBRIDGE_LOG_CONSOLE") == "1" and sys.__stderr__ is not None:
        logger.add(sys.__stderr__, level="DEBUG", format=_FORMAT, colorize=True)


# ---------------------------------------------------------------------------
# std-lib logging → loguru
# ---------------------------------------------------------------------------

class InterceptHandler(logging.Handler):
    """Forward std-lib logging records to loguru, keeping the caller location."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk out of the logging module to find the real caller.
        frame, depth = inspect.currentframe(), 0
        while frame is not None and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _intercept_stdlib_logging() -> None:
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)
    for name in _NOISY_LIBS:
        logging.getLogger(name).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# stdout / stderr → loguru
# ---------------------------------------------------------------------------

class StreamToLogger:
    """
    File-like object that routes print() / stray writes into loguru.

    Writes are line-buffered. A carriage return discards the pending line,
    so tqdm-style progress bars only log their final ("\\n"-terminated) state
    instead of one line per refresh.
    """

    def __init__(self, level: str) -> None:
        self._level = level
        self._buffer = ""
        self._lock = threading.Lock()
        self._guard = threading.local()  # prevents recursion if a sink errors
        self.encoding = "utf-8"
        self.errors = "replace"

    def write(self, message: str) -> int:
        if getattr(self._guard, "active", False):
            return len(message)
        with self._lock:
            data = self._buffer + message
            *lines, self._buffer = data.split("\n")
        self._guard.active = True
        try:
            for line in lines:
                line = line.rsplit("\r", 1)[-1].rstrip()
                if line:
                    logger.opt(depth=1).log(self._level, line)
        finally:
            self._guard.active = False
        with self._lock:
            # A bare "\r" means the line is being redrawn — drop the old content.
            if "\r" in self._buffer:
                self._buffer = self._buffer.rsplit("\r", 1)[-1]
        return len(message)

    def flush(self) -> None:
        pass  # line-buffered; partial lines are kept until the next newline

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("StreamToLogger has no file descriptor")


# ---------------------------------------------------------------------------
# Uncaught exceptions
# ---------------------------------------------------------------------------

def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.opt(exception=(exc_type, exc_value, exc_tb)).critical("Uncaught exception")


def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    thread_name = args.thread.name if args.thread else "?"
    logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).critical(
        "Uncaught exception in thread {}", thread_name
    )


def install_qt_message_handler() -> None:
    """Route Qt's qDebug/qWarning/qCritical output (normally lost under pythonw) into the log."""
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: "DEBUG",
        QtMsgType.QtInfoMsg: "INFO",
        QtMsgType.QtWarningMsg: "WARNING",
        QtMsgType.QtCriticalMsg: "ERROR",
        QtMsgType.QtFatalMsg: "CRITICAL",
    }

    def handler(msg_type, _context, message) -> None:
        logger.bind(channel="ui").log(levels.get(msg_type, "INFO"), "[Qt] {}", message)

    qInstallMessageHandler(handler)


# ---------------------------------------------------------------------------
# Initialise on import
# ---------------------------------------------------------------------------

_configure_sinks()
_intercept_stdlib_logging()

sys.stdout = StreamToLogger("INFO")
# stderr carries progress bars and library warnings far more often than real
# errors; uncaught exceptions are logged as CRITICAL by the excepthooks below.
sys.stderr = StreamToLogger("WARNING")
sys.excepthook = _sys_excepthook
threading.excepthook = _threading_excepthook

app_logger = logger.bind(channel="app")
ui_logger = logger.bind(channel="ui")

__all__ = ["app_logger", "ui_logger", "logger", "install_qt_message_handler", "LOG_DIR"]
