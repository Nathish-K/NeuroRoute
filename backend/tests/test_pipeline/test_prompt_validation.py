"""API-level prompt validation on RequestCreate (Task 9.1a, Requirement 8.7)."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base
from app.database.dependencies import get_db
from app.main import app
from app.models.request import Request
from app.schemas.requests import RequestCreate
from tests.conftest import seed_stub_model, stub_provider

WHITESPACE_ONLY = st.text(
    alphabet=st.characters(whitelist_categories=("Zs",))
    | st.sampled_from(["\t", "\n", "\r", " "]),
    min_size=1,
)
HAS_NON_WHITESPACE = st.text(min_size=1, max_size=1000).filter(lambda s: s.strip())
TOO_LONG = st.text(min_size=1001, max_size=1200)


def _row_count(db_session: Session) -> int:
    db_session.expire_all()
    return db_session.scalar(select(func.count()).select_from(Request))


def _assert_prompt_error(response) -> None:
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail
    assert any(entry["loc"][-1] == "prompt" for entry in detail)


# ---------------------------------------------------------------- examples


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": "\n\t "},
        {},
        {"prompt": 123},
        {"prompt": None},
        {"prompt": "x" * 1001},
    ],
    ids=["empty", "spaces", "mixed-ws", "missing", "int", "null", "1001-chars"],
)
def test_invalid_prompt_returns_422_and_persists_nothing(
    test_client, db_session, payload
):
    response = test_client.post("/api/requests/", json=payload)
    _assert_prompt_error(response)
    assert _row_count(db_session) == 0


@pytest.mark.parametrize(
    "prompt",
    ["x" * 1000, "é" * 1000, "😀" * 1000],
    ids=["ascii-1000", "multibyte-1000", "emoji-1000"],
)
def test_prompt_of_1000_characters_accepted(
    test_client, db_session, pipeline_ready, prompt
):
    response = test_client.post("/api/requests/", json={"prompt": prompt})
    assert response.status_code == 200
    assert response.json()["prompt"] == prompt
    assert _row_count(db_session) == 1


def test_normal_prompt_shape_and_original_text_preserved(
    test_client, db_session, pipeline_ready
):
    response = test_client.post("/api/requests/", json={"prompt": "  hello  "})
    assert response.status_code == 200
    body = response.json()
    # The prompt is stored and returned exactly as submitted, untrimmed.
    assert {"id", "prompt", "status"} <= set(body)
    assert body["prompt"] == "  hello  "
    assert db_session.get(Request, body["id"]).prompt == "  hello  "


def test_surrounding_whitespace_with_content_accepted(test_client, pipeline_ready):
    response = test_client.post("/api/requests/", json={"prompt": "\n a \t"})
    assert response.status_code == 200
    assert response.json()["prompt"] == "\n a \t"


# -------------------------------------------------------------- properties


# Feature: neuroroute-mvp, Task 9.1a / Requirement 8.7
@settings(max_examples=100)
@given(prompt=HAS_NON_WHITESPACE)
def test_property_valid_prompt_accepted_unchanged(prompt: str) -> None:
    assert RequestCreate(prompt=prompt).prompt == prompt


# Feature: neuroroute-mvp, Task 9.1a / Requirement 8.7
@settings(max_examples=100)
@given(prompt=TOO_LONG)
def test_property_overlong_prompt_rejected(prompt: str) -> None:
    with pytest.raises(ValidationError):
        RequestCreate(prompt=prompt)


# Feature: neuroroute-mvp, Task 9.1a / Requirement 8.7
@settings(max_examples=100)
@given(prompt=WHITESPACE_ONLY)
def test_property_whitespace_only_prompt_rejected(prompt: str) -> None:
    with pytest.raises(ValidationError):
        RequestCreate(prompt=prompt)


@pytest.fixture(scope="module")
def http_client() -> Iterator[tuple[TestClient, sessionmaker]]:
    """Module-scoped client with its own SQLite DB (Hypothesis rejects
    function-scoped fixtures, so the HTTP property cannot use test_client)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as session:
        seed_stub_model(session)

    def _override() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    try:
        # The accepted half of the property runs the whole pipeline, so the
        # provider is stubbed for the lifetime of the module.
        with stub_provider():
            yield TestClient(app), factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


# Feature: neuroroute-mvp, Task 9.1a / Requirement 8.7
@settings(max_examples=100, deadline=None)
@given(
    prompt=st.one_of(HAS_NON_WHITESPACE, TOO_LONG, WHITESPACE_ONLY),
)
def test_property_http_acceptance_matches_rule(http_client, prompt: str) -> None:
    client, factory = http_client
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(Request))

    response = client.post("/api/requests/", json={"prompt": prompt})
    should_accept = 1 <= len(prompt) <= 1000 and bool(prompt.strip())

    with factory() as session:
        after = session.scalar(select(func.count()).select_from(Request))

    if should_accept:
        assert response.status_code == 200
        assert response.json()["prompt"] == prompt
        assert after == before + 1
    else:
        assert response.status_code == 422
        assert after == before
