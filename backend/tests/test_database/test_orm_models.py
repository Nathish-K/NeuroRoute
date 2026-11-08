from decimal import Decimal

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.schema import CreateTable

from app import models as m
from app.database.connection import Base


def make_request(db: Session, prompt: str = "hello") -> m.Request:
    request = m.Request(prompt=prompt)
    db.add(request)
    db.commit()
    return request


def make_model(db: Session, identifier: str = "gemini-flash") -> m.Model:
    model = m.Model(
        identifier=identifier,
        provider_name="google",
        model_name="flash",
        max_context_length=8000,
        cost_per_input_token=Decimal("0.0000001000"),
        cost_per_output_token=Decimal("0.0000004000"),
        capability_tier=1,
    )
    db.add(model)
    db.commit()
    return model


def make_decision(db: Session, request: m.Request, model: m.Model) -> m.RoutingDecision:
    decision = m.RoutingDecision(
        request_id=request.id,
        model_id=model.id,
        policy="balanced",
        complexity_class="simple",
        estimated_cost=Decimal("0.0001"),
        explanation="cheapest capable model",
    )
    db.add(decision)
    db.commit()
    return decision


def make_execution(db: Session, decision: m.RoutingDecision, **kw) -> m.Execution:
    execution = m.Execution(routing_decision_id=decision.id, **kw)
    db.add(execution)
    db.commit()
    return execution


def chain(db: Session):
    request = make_request(db)
    model = make_model(db)
    decision = make_decision(db, request, model)
    execution = make_execution(db, decision, response_text="ok", status="completed")
    return request, model, decision, execution


# --- registration ---------------------------------------------------------

def test_all_six_tables_registered():
    assert set(Base.metadata.tables) == {
        "requests", "models", "routing_decisions",
        "executions", "evaluations", "feedback",
    }


def test_configure_mappers_succeeds():
    configure_mappers()


# --- defaults -------------------------------------------------------------

def test_request_defaults(db_session):
    request = make_request(db_session)
    db_session.refresh(request)
    assert request.status == "pending"
    assert request.created_at is not None
    assert request.complexity_class is None
    assert request.end_to_end_latency_ms is None


# --- relationships --------------------------------------------------------

def test_relationships_round_trip(db_session):
    request, model, decision, execution = chain(db_session)
    evaluation = m.Evaluation(
        execution_id=execution.id, quality_score=0.9, confidence=0.8
    )
    feedback = m.Feedback(request_id=request.id, rating=5)
    db_session.add_all([evaluation, feedback])
    db_session.commit()
    db_session.expire_all()

    assert request.routing_decisions == [decision]
    assert request.feedback.rating == 5
    assert decision.request is request
    assert decision.model is model
    assert decision.executions == [execution]
    assert model.routing_decisions == [decision]
    assert execution.routing_decision is decision
    assert execution.evaluation.quality_score == 0.9
    assert evaluation.execution is execution
    assert feedback.request is request


# --- constraints ----------------------------------------------------------

def test_model_identifier_unique(db_session):
    make_model(db_session, "dup")
    with pytest.raises(IntegrityError):
        make_model(db_session, "dup")


def test_evaluation_execution_id_unique(db_session):
    *_, execution = chain(db_session)
    db_session.add(m.Evaluation(execution_id=execution.id, quality_score=1, confidence=1))
    db_session.commit()
    db_session.add(m.Evaluation(execution_id=execution.id, quality_score=2, confidence=2))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_feedback_request_id_unique(db_session):
    request = make_request(db_session)
    db_session.add(m.Feedback(request_id=request.id, rating=1))
    db_session.commit()
    db_session.add(m.Feedback(request_id=request.id, rating=2))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_foreign_key_enforced(db_session):
    model = make_model(db_session)
    db_session.add(m.RoutingDecision(
        request_id=9999, model_id=model.id, policy="p", complexity_class="simple",
        estimated_cost=Decimal("0"), explanation="x",
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --- cascades -------------------------------------------------------------

def test_delete_request_cascades_to_decisions_and_executions(db_session):
    request, model, _decision, _execution = chain(db_session)
    db_session.delete(request)
    db_session.commit()
    assert db_session.query(m.RoutingDecision).count() == 0
    assert db_session.query(m.Execution).count() == 0
    assert db_session.query(m.Model).count() == 1  # models are not cascaded


def test_delete_request_with_feedback_currently_raises(db_session):
    # The design gives Request.feedback no cascade, so SQLAlchemy tries to NULL
    # feedback.request_id (NOT NULL) and the delete fails with IntegrityError.
    # This pins today's behaviour so a future change to it is noticed.
    request = make_request(db_session)
    db_session.add(m.Feedback(request_id=request.id, rating=3))
    db_session.commit()
    db_session.delete(request)
    with pytest.raises(IntegrityError):
        db_session.commit()


# --- large text -----------------------------------------------------------

def test_large_response_text_round_trips(db_session):
    _, _, decision, _ = chain(db_session)
    text = "x" * 100_000
    execution = make_execution(db_session, decision, response_text=text)
    db_session.expire_all()
    assert db_session.get(m.Execution, execution.id).response_text == text


# --- MySQL DDL (offline compile) -------------------------------------------

def _ddl(table: str) -> str:
    return str(CreateTable(Base.metadata.tables[table]).compile(dialect=mysql.dialect()))


def test_mysql_ddl_longtext_for_response_text():
    ddl = _ddl("executions")
    line = next(l for l in ddl.splitlines() if "response_text" in l)
    assert "LONGTEXT" in line


@pytest.mark.parametrize("table, columns", [
    ("models", ["cost_per_input_token", "cost_per_output_token"]),
    ("routing_decisions", ["estimated_cost"]),
    ("executions", ["estimated_cost"]),
])
def test_mysql_ddl_money_columns_numeric_20_10(table, columns):
    ddl = _ddl(table)
    for column in columns:
        line = next(l for l in ddl.splitlines() if column in l)
        assert "NUMERIC(20, 10)" in line
