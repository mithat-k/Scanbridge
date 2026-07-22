"""
logger.py

Centralised logging configuration for Scanbridge.

- Creates a dated log file per logger (e.g. scanbridge_app_2026-07-16.log)
  inside the project's logs/ directory.
- Redirects sys.stdout and sys.stderr to the application logger via a
  StreamToLogger pipeline, so no terminal window is required at runtime.
- Provides two ready-to-import loggers:
    app_logger  – general application / engine events
    ui_logger   – UI Engine specific events (separate log file)
"""

import logging
import os
import sys
from datetime import datetime

# Root directory for all log files (created automatically if absent)
LOG_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def get_log_file_path(name: str) -> str:
    """Return the dated log file path for the given logger name.

    Args:
        name: Base name for the log file (e.g. 'scanbridge_app', 'ui_engine').
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{name}_{date_str}.log")


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create and configure a file-only logger (no console / StreamHandler).

    Because the application runs without a terminal window (.pyw), all output
    is written exclusively to a rotating daily log file.

    Args:
        name:  Logger name — also used as the log file base name.
        level: Minimum log level (default INFO).
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Attach a handler only on the first call to avoid duplicate log entries
    if not logger.handlers:
        log_path = get_log_file_path(name)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Prevent log records from propagating to the root logger's handlers
        # (which could write to the console and break the no-terminal contract)
        logger.propagate = False

    return logger


# Ready-to-use loggers — import these throughout the project
app_logger = setup_logger("scanbridge_app", logging.INFO)
ui_logger  = setup_logger("ui_engine",      logging.DEBUG)


class StreamToLogger:
    """
    File-like object that captures stdout / stderr writes and routes them
    into the specified logger (pipeline mode).

    This allows any print() call or uncaught exception traceback to appear
    in the log file even when the application runs without a terminal.
    """

    def __init__(self, logger: logging.Logger, log_level: int) -> None:
        self.logger    = logger
        self.log_level = log_level
        self.encoding  = "utf-8"
        self.errors    = "replace"

    def write(self, message: str) -> None:
        # Skip bare newlines to keep the log tidy
        if message != "\n":
            for line in message.rstrip().splitlines():
                self.logger.log(self.log_level, line.rstrip())

    def flush(self) -> None:
        pass  # Required by the file-like interface; nothing to flush

    def isatty(self) -> bool:
        return False


# Redirect standard streams to the pipeline so the terminal stays silent
sys.stdout = StreamToLogger(app_logger, logging.INFO)
sys.stderr = StreamToLogger(app_logger, logging.ERROR)

__all__ = ["app_logger", "ui_logger", "setup_logger"]
