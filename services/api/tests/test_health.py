from fastapi.testclient import TestClient

from services.api.app.main import app


client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    # Basic sanity check that Prometheus text output is present
    assert b"# HELP" in response.content
    assert b"api_request_count_total" in response.content