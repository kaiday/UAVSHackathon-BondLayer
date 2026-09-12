"""Structured logging for AgentBridge.

Every tool call is logged as one JSON line, so the whole agent
conversation is auditable and the benchmark can count steps.

IMPORTANT: the MCP server speaks JSON-RPC over stdout, so logs go to
stderr and to `agentbridge.log` — never stdout.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_FILE = Path(__file__).resolve().parent.parent / "agentbridge.log"


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


def get_logger(name: str = "agentbridge") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = JsonLineFormatter()
    stderr_handler = logging.StreamHandler(sys.stderr)  # NOT stdout: stdio MCP transport
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass  # read-only fs etc. — stderr alone is fine
    return logger


def log_event(event: str, **data: Any) -> None:
    """Log one structured event, e.g. log_event('tool_call', tool='create_order', ...)."""
    get_logger().info(event, extra={"data": data})
