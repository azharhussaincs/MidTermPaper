"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.execution_logger import ExecutionLogger, set_execution_logger
from app.db.database import dispose_db, init_db


@pytest.fixture
def temp_db(tmp_path: Path) -> Iterator[Path]:
    """A fresh SQLite database per test; the app's real DB is never touched."""
    db_path = tmp_path / "test_mental_health_agent.db"
    init_db(db_path)
    yield db_path
    dispose_db()


@pytest.fixture(autouse=True)
def execution_trace(tmp_path: Path) -> Iterator[ExecutionLogger]:
    """Every test gets its own in-memory + JSONL trace; the real logs/ dir is never written."""
    tracer = ExecutionLogger(tmp_path / "execution_trace.jsonl", keep_runs=True)
    set_execution_logger(tracer)
    yield tracer
    set_execution_logger(None)
