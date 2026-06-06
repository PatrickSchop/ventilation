import logging
from logging.handlers import RotatingFileHandler
import os
import traceback

_logger = None

def _setupLogger():
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("ventilation")
    _logger.setLevel(logging.INFO)

    # Use an absolute path so the log file lands somewhere writable regardless
    # of CWD (matters under systemd where WorkingDirectory may not be set).
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ventilation.log")
    try:
        handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )
        _logger.addHandler(handler)
    except (OSError, IOError) as e:
        # Fall back to a console-only logger so we don't lose the error.
        print(f"Logger: file handler setup failed ({e}); using console only")
    return _logger


class Logger:
    @staticmethod
    def error(err):
        print(err)
        if isinstance(err, BaseException):
            traceback_str = "".join(traceback.format_tb(err.__traceback__))
            print(traceback_str)
        log = _setupLogger()
        log.error(str(err))

    @staticmethod
    def warning(msg):
        print(msg)
        log = _setupLogger()
        log.warning(msg)

    @staticmethod
    def info(msg):
        print(msg)
        log = _setupLogger()
        log.info(msg)

    @staticmethod
    def fault(category: str, msg: str):
        Logger.error(f"[ERROR:{category}] {msg}")

    @staticmethod
    def recovery(category: str, msg: str):
        Logger.info(f"[RECOVERY:{category}] {msg}")
