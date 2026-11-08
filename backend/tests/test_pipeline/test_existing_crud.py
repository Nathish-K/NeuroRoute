from app.models.request import Request


def test_post_creates_request(test_client, db_session):
    response = test_client.post("/api/requests/", json={"prompt": "Explain RAG"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "prompt", "status"}
    assert body["prompt"] == "Explain RAG"
    assert body["status"] == "pending"

    row = db_session.get(Request, body["id"])
    assert row is not None and row.prompt == "Explain RAG"


def test_get_lists_newest_first(test_client):
    ids = [
        test_client.post("/api/requests/", json={"prompt": f"p{i}"}).json()["id"]
        for i in range(3)
    ]
    response = test_client.get("/api/requests/")
    assert response.status_code == 200
    body = response.json()
    assert [r["id"] for r in body] == sorted(ids, reverse=True)
    assert all(set(r) == {"id", "prompt", "status"} for r in body)


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
