import logging
from logging.handlers import RotatingFileHandler
import traceback

_logger = None

def _setupLogger():
    global _logger
    if _logger is not None:
        return _logger

    handler = RotatingFileHandler(
        "ventilation.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    )

    _logger = logging.getLogger("ventilation")
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
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
