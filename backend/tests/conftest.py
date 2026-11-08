"""Shared pytest fixtures for the NeuroRoute backend suite.

Every test runs against in-memory SQLite. An autouse guard blocks the live
MySQL engine/session so a test can never touch the real ``neuroroute`` data.
"""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  (registers every table on Base)
from app.database import connection as _connection
from app.database import dependencies as _dependencies
from app.database.connection import Base
from app.database.dependencies import get_db
from app.main import app

LIVE_DB_MESSAGE = "Tests must not use the live MySQL session"


def _blocked(*_args, **_kwargs):
    raise RuntimeError(LIVE_DB_MESSAGE)


@pytest.fixture(autouse=True)
def block_live_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any use of the live MySQL session or engine raise RuntimeError."""
    monkeypatch.setattr(_connection, "SessionLocal", _blocked)
    monkeypatch.setattr(_dependencies, "SessionLocal", _blocked)
    # Engine is a plain object (no __slots__), so instance attributes can be patched.
    monkeypatch.setattr(_connection.engine, "connect", _blocked)
    monkeypatch.setattr(_connection.engine, "begin", _blocked)


@pytest.fixture()
def engine() -> Iterator[Engine]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def test_client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
