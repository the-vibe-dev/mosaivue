from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, event
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .constants import DB_PATH


class Base(DeclarativeBase):
    pass


def create_engine(path: Path | str | None = None) -> Engine:
    db_path = Path(path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = sa_create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: sqlite3.Connection, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def configure_database(path: Path | str | None = None) -> Engine:
    global _engine, _SessionLocal
    _engine = create_engine(path)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        configure_database()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        configure_database()
    assert _SessionLocal is not None
    return _SessionLocal


def init_db(path: Path | str | None = None) -> Engine:
    if path is not None or _engine is None:
        engine = configure_database(path)
    else:
        engine = get_engine()
    # Import models before metadata creation.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return engine


@contextlib.contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def session_dependency() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session
