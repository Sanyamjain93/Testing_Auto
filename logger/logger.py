import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

os.makedirs(LOG_DIR, exist_ok=True)

_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Tracks the current run-specific file handler so it can be replaced on the next run
_file_handler: logging.FileHandler | None = None


def _configure_root() -> None:
    """Set up the console handler on the root project logger exactly once."""
    root = logging.getLogger("test_automation")
    if root.handlers:
        return  # already configured

    root.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    root.propagate = False  # do not bubble up to the Python root logger

    # CONSOLE handler — INFO+ only (keeps terminal clean)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(_formatter)
    root.addHandler(ch)


def new_run_log() -> str:
    """
    Create a fresh timestamped log file for a new pipeline run.

    Replaces the previous run's file handler (if any) so each run gets
    its own isolated log file.  Returns the path of the new log file.

    Filename format: logs/YYYY-MM-DD_HH-MM-SS_run.log
    """
    global _file_handler

    _configure_root()
    root = logging.getLogger("test_automation")

    # Remove the previous run's file handler
    if _file_handler is not None:
        root.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(LOG_DIR, f"{timestamp}_run.log")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_formatter)
    root.addHandler(fh)
    _file_handler = fh

    return log_file


def get_logger(name: str = "test_automation") -> logging.Logger:
    """
    Return a logger under the 'test_automation' hierarchy.

    The root project logger is configured with:
      - FileHandler  → logs/<timestamp>_run.log  (DEBUG+, created per pipeline run)
      - StreamHandler → console                  (INFO+)

    Child loggers (e.g. 'test_automation.pipeline') inherit both handlers
    via propagation without duplicating them.
    """
    _configure_root()
    logger = logging.getLogger(name)
    if name != "test_automation":
        logger.setLevel(logging.DEBUG)
    return logger
