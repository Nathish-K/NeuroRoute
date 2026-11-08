"""Model Registry API tests (Task 2.3, Requirements 1.1, 1.2, 1.3, 1.4, 1.7)."""
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base
from app.database.dependencies import get_db
from app.main import app
from app.models.model import Model

URL = "/api/models/"
RESPONSE_FIELDS = {
    "id", "identifier", "provider_name", "model_name", "max_context_length",
    "cost_per_input_token", "cost_per_output_token", "capability_tier",
    "enabled", "created_at",
}
REQUIRED_FIELDS = {
    "identifier", "provider_name", "model_name", "max_context_length",
    "cost_per_input_token", "cost_per_output_token",
}


def model_payload(identifier: str = "gemini-flash", **overrides) -> dict:
    payload = {
        "identifier": identifier,
        "provider_name": "google",
        "model_name": "gemini-2.0-flash",
        "max_context_length": 1_000_000,
        "cost_per_input_token": "0.0000001000",
        "cost_per_output_token": "0.0000004000",
    }
    payload.update(overrides)
    return payload


def _sort_key(model: dict) -> tuple[str, str]:
    return (model["provider_name"], model["model_name"])


# ------------------------------------------------------------------ unit tests


def test_post_creates_model_and_returns_201_with_all_fields(test_client, db_session):
    response = test_client.post(URL, json=model_payload(capability_tier=2))

    assert response.status_code == 201
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert isinstance(body["id"], int)
    assert body["created_at"]
    assert body["identifier"] == "gemini-flash"
    assert body["provider_name"] == "google"
    assert body["model_name"] == "gemini-2.0-flash"
    assert body["max_context_length"] == 1_000_000
    assert Decimal(body["cost_per_input_token"]) == Decimal("0.0000001")
    assert Decimal(body["cost_per_output_token"]) == Decimal("0.0000004")
    assert body["capability_tier"] == 2
    assert body["enabled"] is True  # default when not supplied (Requirement 1.1)

    stored = db_session.get(Model, body["id"])
    assert stored is not None and stored.identifier == "gemini-flash"


def test_get_returns_models_ordered_by_provider_then_model_name(test_client):
    inserted = [
        ("m1", "ollama", "qwen2.5:3b"),
        ("m2", "google", "gemini-pro"),
        ("m3", "anthropic", "claude"),
        ("m4", "google", "gemini-flash"),
    ]
    for identifier, provider, name in inserted:
        response = test_client.post(
            URL, json=model_payload(identifier, provider_name=provider, model_name=name)
        )
        assert response.status_code == 201

    response = test_client.get(URL)

    assert response.status_code == 200
    assert [(m["provider_name"], m["model_name"]) for m in response.json()] == [
        ("anthropic", "claude"),
        ("google", "gemini-flash"),
        ("google", "gemini-pro"),
        ("ollama", "qwen2.5:3b"),
    ]


def test_get_with_no_models_returns_empty_list(test_client):
    response = test_client.get(URL)
    assert response.status_code == 200
    assert response.json() == []


def test_duplicate_identifier_returns_409_and_persists_nothing(test_client, db_session):
    assert test_client.post(URL, json=model_payload("dup")).status_code == 201

    response = test_client.post(URL, json=model_payload("dup", provider_name="ollama"))

    assert response.status_code == 409
    # Requirement 1.4: message identifies the conflicting field and its value.
    assert response.json() == {"detail": "Model with identifier 'dup' already exists"}
    assert len(db_session.scalars(select(Model)).all()) == 1


@pytest.mark.parametrize("missing", sorted(REQUIRED_FIELDS))
def test_missing_required_field_returns_422_naming_it(test_client, db_session, missing):
    payload = model_payload()
    del payload[missing]

    response = test_client.post(URL, json=payload)

    assert response.status_code == 422
    missing_locs = {
        entry["loc"][-1] for entry in response.json()["detail"] if entry["type"] == "missing"
    }
    assert missing_locs == {missing}
    assert db_session.scalars(select(Model)).all() == []


def test_every_missing_required_field_is_named(test_client):
    # Requirement 1.5: each missing field is identified by name.
    response = test_client.post(URL, json={})

    assert response.status_code == 422
    missing_locs = {
        entry["loc"][-1] for entry in response.json()["detail"] if entry["type"] == "missing"
    }
    assert missing_locs == REQUIRED_FIELDS


def test_disabled_model_still_appears_in_get(test_client):
    test_client.post(URL, json=model_payload("on"))
    test_client.post(URL, json=model_payload("off", model_name="gemini-pro", enabled=False))

    response = test_client.get(URL)

    assert response.status_code == 200
    by_identifier = {m["identifier"]: m for m in response.json()}
    assert set(by_identifier) == {"on", "off"}
    assert by_identifier["off"]["enabled"] is False


# ------------------------------------------------------------------ properties
# Hypothesis rejects function-scoped fixtures, so properties share one SQLite
# database per module and clear the models table at the start of each example.

# Restricted to lowercase ASCII so ordering is identical under SQLite's binary
# collation and MySQL's case-insensitive utf8mb4_0900_ai_ci collation.
NAME_TEXT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.:", min_size=1, max_size=40)
IDENTIFIER_TEXT = st.text(
    alphabet=st.characters(
        min_codepoint=33, max_codepoint=0x2FFF, blacklist_categories=("Cc", "Cs", "Zs")
    ),
    min_size=1,
    max_size=128,
)
# Kept to realistic per-token prices so values survive SQLite's float-backed
# Numeric storage exactly; MySQL stores DECIMAL(20,10) natively.
COST = st.decimals(min_value=0, max_value=Decimal("0.01"), places=10, allow_nan=False, allow_infinity=False)

MODEL_CREATE = st.fixed_dictionaries(
    {
        "identifier": IDENTIFIER_TEXT,
        "provider_name": st.text(min_size=1, max_size=128).filter(lambda s: "\x00" not in s),
        "model_name": st.text(min_size=1, max_size=256).filter(lambda s: "\x00" not in s),
        "max_context_length": st.integers(min_value=1, max_value=2_000_000_000),
        "cost_per_input_token": COST,
        "cost_per_output_token": COST,
        "capability_tier": st.integers(min_value=1, max_value=3),
        "enabled": st.booleans(),
    }
)


@pytest.fixture(scope="module")
def registry_db() -> Iterator[sessionmaker]:
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
    try:
        yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    finally:
        engine.dispose()


def _fresh_client(factory: sessionmaker) -> TestClient:
    """Empty the models table and point get_db at the module database.

    The override is reapplied per example because the function-scoped
    ``test_client`` fixture clears ``app.dependency_overrides`` on teardown.
    """
    with factory() as session:
        session.execute(delete(Model))
        session.commit()

    def _override() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _clear_overrides_after_module() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _json_ready(payload: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in payload.items()}


# Feature: neuroroute-mvp, Property 1: Model Registry Round-Trip
# Validates: Requirements 1.1, 1.3
@settings(max_examples=100, deadline=None)
@given(payload=MODEL_CREATE)
def test_property_round_trip(registry_db, payload: dict) -> None:
    client = _fresh_client(registry_db)

    created = client.post(URL, json=_json_ready(payload))
    assert created.status_code == 201, created.text

    listed = client.get(URL)
    assert listed.status_code == 200
    matches = [m for m in listed.json() if m["identifier"] == payload["identifier"]]
    assert len(matches) == 1
    fetched = matches[0]

    for field, submitted in payload.items():
        if isinstance(submitted, Decimal):
            assert Decimal(fetched[field]) == submitted, field
        else:
            assert fetched[field] == submitted, field
    assert fetched["id"] == created.json()["id"]


# Feature: neuroroute-mvp, Property 2: Model List Ordering
# Validates: Requirements 1.2
@settings(max_examples=100, deadline=None)
@given(names=st.lists(st.tuples(NAME_TEXT, NAME_TEXT), min_size=0, max_size=12))
def test_property_list_ordering(registry_db, names: list[tuple[str, str]]) -> None:
    client = _fresh_client(registry_db)
    for index, (provider, model_name) in enumerate(names):
        response = client.post(
            URL,
            json=model_payload(f"model-{index}", provider_name=provider, model_name=model_name),
        )
        assert response.status_code == 201

    listed = client.get(URL).json()

    assert len(listed) == len(names)
    keys = [_sort_key(m) for m in listed]
    assert keys == sorted(names)


# Feature: neuroroute-mvp, Property 3: Disabled Models Excluded from Routing
# Validates: Requirements 1.7, 3.3, 3.4
# The routing selectors (select_cost_optimised etc.) do not exist until Task 5.x,
# which re-validates this property against them. Here it pins the registry side:
# the enabled-only query the router depends on returns exactly the enabled
# models, while GET /api/models/ still lists every model (Requirement 1.7).
@settings(max_examples=100, deadline=None)
@given(flags=st.lists(st.booleans(), min_size=0, max_size=12))
def test_property_disabled_models_excluded_from_routing(registry_db, flags: list[bool]) -> None:
    client = _fresh_client(registry_db)
    for index, enabled in enumerate(flags):
        response = client.post(URL, json=model_payload(f"model-{index}", enabled=enabled))
        assert response.status_code == 201

    with registry_db() as session:
        routable = session.scalars(select(Model).where(Model.enabled.is_(True))).all()

    expected_enabled = {f"model-{i}" for i, enabled in enumerate(flags) if enabled}
    assert {m.identifier for m in routable} == expected_enabled
    assert all(m.enabled is True for m in routable)

    listed = client.get(URL).json()
    assert {m["identifier"] for m in listed} == {f"model-{i}" for i in range(len(flags))}
