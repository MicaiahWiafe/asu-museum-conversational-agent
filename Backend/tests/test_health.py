from fastapi.testclient import TestClient

from main import app, get_vector_store


class _StubStore:
    def count(self) -> int:
        return 0

    def query(self, *args, **kwargs):
        return []

    def add_chunks(self, *args, **kwargs):
        pass

    def delete_by_source(self, *args, **kwargs):
        pass


def test_health_returns_ok_status_field():
    app.dependency_overrides[get_vector_store] = lambda: _StubStore()
    try:
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("ok", "degraded")
        assert body["vector_store"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_session_start_returns_session_id():
    client = TestClient(app)
    resp = client.post("/session/start", json={"language": "en"})
    assert resp.status_code == 200
    assert "session_id" in resp.json()
    assert len(resp.json()["session_id"]) > 0
