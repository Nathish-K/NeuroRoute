import pytest

from app.database import connection, dependencies
from app.database.dependencies import get_db
from app.main import app


def test_live_session_local_is_blocked():
    with pytest.raises(RuntimeError, match="live MySQL"):
        connection.SessionLocal()
    with pytest.raises(RuntimeError, match="live MySQL"):
        dependencies.SessionLocal()


def test_live_get_db_is_blocked():
    with pytest.raises(RuntimeError, match="live MySQL"):
        next(dependencies.get_db())


def test_live_engine_is_blocked():
    with pytest.raises(RuntimeError, match="live MySQL"):
        connection.engine.connect()
    with pytest.raises(RuntimeError, match="live MySQL"):
        connection.engine.begin()


def test_client_override_points_at_sqlite(test_client):
    override = app.dependency_overrides[get_db]
    session = next(override())
    try:
        assert session.bind.dialect.name == "sqlite"
    finally:
        session.close()


def test_overrides_cleared_after_fixture():
    assert get_db not in app.dependency_overrides
