import logging
import re

SENSITIVE_PATTERNS = [
    (re.compile(r"C:\\Users\\[^\\]+"), r"C:\\Users\\***"),
    (re.compile(r"/home/[^/]+"), r"/home/***"),
    (re.compile(r"/Users/[^/]+"), r"/Users/***"),
]


def sanitize_path(path: str) -> str:
    result = str(path)
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_message(message: str) -> str:
    result = str(message)
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


class SecureLogger:
    def __init__(self, name: str):
        self._logger = setup_logger(name)

    def info(self, message: str, *args, **kwargs):
        self._logger.info(sanitize_message(message), *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        self._logger.warning(sanitize_message(message), *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        self._logger.error(sanitize_message(message), *args, **kwargs)

    def debug(self, message: str, *args, **kwargs):
        self._logger.debug(sanitize_message(message), *args, **kwargs)
