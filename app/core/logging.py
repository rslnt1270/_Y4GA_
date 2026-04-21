# © YAGA Project — Todos los derechos reservados
"""
Logging JSON estructurado para YAGA.
Sprint 6 — Observabilidad centralizada.
"""
import json
import logging
import sys
import traceback
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formateador que emite cada log como una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc_info"] = traceback.format_exception(*record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """Configura el root logger con formato JSON a stdout."""
    root = logging.getLogger()
    if any(
        isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter)
        for h in root.handlers
    ):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger con nombre de módulo específico."""
    return logging.getLogger(name)
