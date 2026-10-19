"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

from eve import models  # noqa: F401  (registers tables on SQLModel.metadata)


def make_engine(db_path: Path | None) -> Engine:
    url = "sqlite://" if db_path is None else f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")  # STT thread writes while API reads
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
        try:
            import sqlite_vec

            dbapi_conn.enable_load_extension(True)
            sqlite_vec.load(dbapi_conn)
            dbapi_conn.enable_load_extension(False)
        except Exception:
            pass

    SQLModel.metadata.create_all(engine)

    from eve.rag.index import init_rag_tables

    init_rag_tables(engine)
    return engine


def session_scope(engine: Engine) -> Iterator[DBSession]:
    with DBSession(engine) as db:
        yield db
