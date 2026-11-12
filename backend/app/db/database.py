"""SQLAlchemy engines and sessions for the SQLite assessment store.

Sync engine: used by LangChain tools (LangGraph runs sync tools in a worker thread).
Async engine: used by FastAPI request handlers.
Both point at the same file; WAL mode lets them read/write concurrently.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_async_engine: AsyncEngine | None = None
_session_factory: sessionmaker[Session] | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_db(db_path: str | Path | None = None, *, echo: bool = False) -> Engine:
    """Create engines for `db_path` (default: DATABASE_PATH) and create tables.

    Calling it again with another path (e.g. a test database) rebinds everything.
    """
    global _engine, _async_engine, _session_factory, _async_session_factory
    dispose_db()

    path = Path(db_path) if db_path is not None else get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(f"sqlite:///{path}", echo=echo, connect_args={"check_same_thread": False})
    event.listen(_engine, "connect", _set_sqlite_pragmas)
    _async_engine = create_async_engine(f"sqlite+aiosqlite:///{path}", echo=echo)
    event.listen(_async_engine.sync_engine, "connect", _set_sqlite_pragmas)

    _session_factory = sessionmaker(_engine, expire_on_commit=False)
    _async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)

    from app.db import models  # noqa: F401  (register tables on Base.metadata)

    Base.metadata.create_all(_engine)
    return _engine


def dispose_db() -> None:
    global _engine, _async_engine, _session_factory, _async_session_factory
    if _engine is not None:
        _engine.dispose()
    if _async_engine is not None:
        _async_engine.sync_engine.dispose()
    _engine = _async_engine = None
    _session_factory = _async_session_factory = None


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error."""
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    if _async_session_factory is None:
        init_db()
    assert _async_session_factory is not None
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
