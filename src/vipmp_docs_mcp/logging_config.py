"""
Structured file logging for the MCP server.

MCP servers run as subprocesses of the MCP client (e.g. Claude Desktop), so
stdout is reserved for the JSON-RPC transport — we cannot log to stdout.
Everything goes to a rotating file under the user's cache directory.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _cache_dir() -> Path:
    """Resolve the user-level cache directory for this server."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = base / "swo-adobe-vipm-docs-mcp"
    path.mkdir(parents=True, exist_ok=True)
    return path


CACHE_DIR = _cache_dir()
LOG_FILE = CACHE_DIR / "server.log"


def configure_logging(level: str | int = "INFO") -> logging.Logger:
    """Configure the root logger for the package. Idempotent."""
    logger = logging.getLogger("vipmp_docs_mcp")

    # Don't double-configure if called twice.
    if getattr(logger, "_configured", False):
        return logger

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(level)

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,  # 1 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Tag as configured so subsequent calls no-op.
    logger._configured = True  # type: ignore[attr-defined]

    logger.info("logging configured at level=%s file=%s", logging.getLevelName(level), LOG_FILE)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the package namespace."""
    return logging.getLogger(f"vipmp_docs_mcp.{name}")
