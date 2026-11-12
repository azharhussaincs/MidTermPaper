"""LangGraph SqliteSaver checkpointer lifecycle."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import get_settings


def create_checkpointer(db_path: str | Path | None = None) -> SqliteSaver:
    """Open a SqliteSaver on `db_path` (default: CHECKPOINT_DB_PATH).

    `check_same_thread=False` because FastAPI runs sync graph calls in a thread pool;
    SqliteSaver serialises access with its own lock.
    """
    path = Path(db_path) if db_path is not None else get_settings().checkpoint_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def close_checkpointer(saver: SqliteSaver) -> None:
    saver.conn.close()
