"""Backward compatibility of the request endpoints after Task 9.2.

The pipeline replaced the body that ``POST /api/requests/`` returns, so these
tests pin what must not change: the request body it accepts, the fields the
frontend already reads, newest-first ordering, and the health and CORS
behaviour.
"""

from app.models.request import Request

LEGACY_SUMMARY_FIELDS = {"id", "prompt", "status"}


def test_post_accepts_a_plain_prompt_body(test_client, db_session, pipeline_ready):
    response = test_client.post("/api/requests/", json={"prompt": "Explain RAG"})

    assert response.status_code == 200
    body = response.json()
    # The pipeline added fields; the original three are still there.
    assert LEGACY_SUMMARY_FIELDS <= set(body)
    assert body["prompt"] == "Explain RAG"
    assert body["status"] == "completed"

    row = db_session.get(Request, body["id"])
    assert row is not None and row.prompt == "Explain RAG"


def test_post_returns_every_pipeline_block(test_client, pipeline_ready):
    body = test_client.post(
        "/api/requests/", json={"prompt": "Explain RAG"}
    ).json()

    assert body["complexity_class"] == "simple"
    assert body["routing"]["policy"] == "cost_optimised"
    assert body["execution"]["status"] == "completed"
    assert body["evaluation"]["quality_score"] >= 0.0
    assert body["end_to_end_latency_ms"] >= 0
    assert body["step_errors"] == []


def test_get_lists_newest_first(test_client, pipeline_ready):
    ids = [
        test_client.post("/api/requests/", json={"prompt": f"p{i}"}).json()["id"]
        for i in range(3)
    ]

    response = test_client.get("/api/requests/")

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == sorted(ids, reverse=True)
    assert all(LEGACY_SUMMARY_FIELDS <= set(row) for row in body)


def test_health(test_client):
    response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "message": "NeuroRoute backend is running",
    }


def test_cors_allows_dev_origin(test_client):
    response = test_client.get(
        "/api/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
