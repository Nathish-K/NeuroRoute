"""Permanent evidence for the exception hierarchy in app/exceptions.py."""
import inspect

import pydantic
import pytest

from app import exceptions
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

ALL = [
    NeuroRouteError,
    ServiceUnavailableError,
    NoEligibleModelError,
    PersistenceError,
    ConfigurationError,
    ValidationError,
    NotFoundError,
    ConflictError,
]
STATUS = {
    ServiceUnavailableError: "503",
    NoEligibleModelError: "503",
    PersistenceError: "500",
    ConfigurationError: "500",
    ValidationError: "422",
    NotFoundError: "404",
    ConflictError: "409",
}


def test_module_defines_exactly_eight_classes() -> None:
    defined = {
        c
        for _, c in inspect.getmembers(exceptions, inspect.isclass)
        if c.__module__ == exceptions.__name__
    }
    assert defined == set(ALL)
    assert len(defined) == 8


@pytest.mark.parametrize("cls", ALL)
def test_all_subclass_base_and_exception(cls: type) -> None:
    assert issubclass(cls, NeuroRouteError)
    assert issubclass(cls, Exception)


def test_only_no_eligible_model_subclasses_service_unavailable() -> None:
    for cls in ALL:
        expected = cls is NoEligibleModelError or cls is ServiceUnavailableError
        assert issubclass(cls, ServiceUnavailableError) is expected


@pytest.mark.parametrize("cls", [c for c in ALL if c is not NoEligibleModelError and c is not NeuroRouteError])
def test_direct_base_is_neuroroute_error(cls: type) -> None:
    assert cls.__bases__ == (NeuroRouteError,)


def test_no_eligible_model_direct_base() -> None:
    assert NoEligibleModelError.__bases__ == (ServiceUnavailableError,)


@pytest.mark.parametrize("cls,status", list(STATUS.items()))
def test_docstring_states_http_status(cls: type, status: str) -> None:
    assert cls.__doc__ and cls.__doc__.strip()
    assert status in cls.__doc__


def test_raise_catch_round_trip() -> None:
    with pytest.raises(ServiceUnavailableError):
        raise NoEligibleModelError("x")
    with pytest.raises(NeuroRouteError):
        raise NoEligibleModelError("x")
    assert str(NoEligibleModelError("x")) == "x"


def test_validation_error_is_not_pydantic_validation_error() -> None:
    assert exceptions.ValidationError is not pydantic.ValidationError
