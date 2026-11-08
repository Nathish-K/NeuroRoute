"""Tests for the exception handlers registered in app/main.py."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.exceptions import (
    ConfigurationError,
    ConflictError,
    NeuroRouteError,
    NoEligibleModelError,
    NotFoundError,
    PersistenceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.main import app

MAPPED = {
    "NotFoundError": (NotFoundError, 404),
    "ConflictError": (ConflictError, 409),
    "ValidationError": (ValidationError, 422),
    "ServiceUnavailableError": (ServiceUnavailableError, 503),
    "NoEligibleModelError": (NoEligibleModelError, 503),
    "PersistenceError": (PersistenceError, 500),
    "ConfigurationError": (ConfigurationError, 500),
}


class UnmappedError(NeuroRouteError):
    """Custom subclass with no registered handler."""


@pytest.fixture()
def raising_app() -> Iterator[None]:
    """Temporarily add /__test__ routes that raise; always removed in teardown."""
    before = list(app.router.routes)

    @app.get("/__test__/raise/{name}")
    def _raise(name: str, message: str = "boom") -> None:
        if name == "NeuroRouteError":
            raise NeuroRouteError(message)
        if name == "UnmappedError":
            raise UnmappedError(message)
        raise MAPPED[name][0](message)

    try:
        yield
    finally:
        app.router.routes[:] = before
        assert not any(
            getattr(r, "path", "").startswith("/__test__") for r in app.routes
        )


@pytest.mark.parametrize("name", list(MAPPED))
def test_mapped_exception_status_and_body(raising_app: None, name: str) -> None:
    _, status = MAPPED[name]
    response = TestClient(app).get(f"/__test__/raise/{name}", params={"message": "msg here"})
    assert response.status_code == status
    assert response.json() == {"detail": "msg here"}


def test_no_eligible_model_has_own_handler() -> None:
    handlers = app.exception_handlers
    assert NoEligibleModelError in handlers
    assert ServiceUnavailableError in handlers
    assert handlers[NoEligibleModelError] is not handlers[ServiceUnavailableError]


@pytest.mark.parametrize("name", ["NeuroRouteError", "UnmappedError"])
def test_unmapped_errors_return_generic_500(raising_app: None, name: str) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(f"/__test__/raise/{name}", params={"message": "internal-detail"})
    assert response.status_code == 500
    text = response.text
    assert "Traceback" not in text
    assert "internal-detail" not in text
    assert "NeuroRouteError" not in text
    assert "UnmappedError" not in text


def test_configuration_error_returns_variable_name(raising_app: None) -> None:
    response = TestClient(app).get(
        "/__test__/raise/ConfigurationError",
        params={"message": "GEMINI_API_KEY is not set"},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "GEMINI_API_KEY is not set"}


def test_handlers_echo_message_so_secrets_must_never_be_in_messages(
    raising_app: None,
) -> None:
    # Documents current behaviour: the handler echoes str(exc) verbatim.
    # Therefore code that raises these errors must NEVER put secrets in messages.
    response = TestClient(app).get(
        "/__test__/raise/ConfigurationError", params={"message": "bad key sk-FAKE-SECRET"}
    )
    assert response.json() == {"detail": "bad key sk-FAKE-SECRET"}


def test_registered_neuroroute_handlers_are_exactly_the_seven() -> None:
    registered = {
        c
        for c in app.exception_handlers
        if isinstance(c, type) and issubclass(c, NeuroRouteError)
    }
    assert registered == {cls for cls, _ in MAPPED.values()}
    assert NeuroRouteError not in app.exception_handlers


def test_health_endpoint_unchanged() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "message": "NeuroRoute backend is running",
    }


def test_cors_allows_only_dev_origin() -> None:
    client = TestClient(app)
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert bad.headers.get("access-control-allow-origin") != "http://evil.example"
    assert "access-control-allow-origin" not in bad.headers
