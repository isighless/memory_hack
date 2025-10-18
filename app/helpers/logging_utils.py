from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


LOG_FILE_NAME = 'memory_hack.log'


def _root_directory() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parents[2]


def get_log_directory() -> Path:
    """Return the directory that stores server logs, creating it if necessary."""
    log_dir = _root_directory() / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file_path() -> Path:
    """Return the path to the main Memory Hack log file."""
    return get_log_directory() / LOG_FILE_NAME


def read_log_tail(line_limit: int = 400) -> List[str]:
    """Return the last ``line_limit`` lines from the log file."""
    path = get_log_file_path()
    if not path.exists():
        return []

    limit = max(1, min(line_limit, 5000))
    with path.open('r', encoding='utf-8', errors='replace') as handle:
        lines = deque(handle, maxlen=limit)
    return [line.rstrip('\n') for line in lines]


def get_log_metadata() -> Dict[str, object]:
    """Return basic metadata (size and modified time) for the log file."""
    path = get_log_file_path()
    if not path.exists():
        return {'exists': False, 'size': 0, 'modified_at': None}

    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return {
        'exists': True,
        'size': stat.st_size,
        'modified_at': modified,
        'name': path.name,
    }


def clear_log_file() -> None:
    """Truncate the log file while accounting for active logging handlers."""
    path = get_log_file_path()
    root_logger = logging.getLogger()

    handlers = [
        handler for handler in root_logger.handlers
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == path
    ]

    for handler in handlers:
        handler.acquire()
        try:
            handler.close()
        finally:
            handler.release()

    if path.exists():
        path.write_text('', encoding='utf-8')
    else:
        path.touch()

    for handler in handlers:
        handler.acquire()
        try:
            handler.stream = handler._open()
        finally:
            handler.release()
