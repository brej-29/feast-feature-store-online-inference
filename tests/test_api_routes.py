import os

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import app

client = TestClient(app)


def test_health_route():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_route_exists():
    response = client.post("/api/predict", json={"entity_ids": {}, "request": {}})
    assert response.status_code in (200, 422)


@pytest.mark.skipif(
    not os.getenv("POSTGRES_HOST"),
    reason="Postgres not configured; skipping Feast API route tests.",
)
def test_feast_routes_exist_without_crashing():
    # Feast health may return 500 if registry or DB is not configured, but the route should exist.
    resp_health = client.get("/api/feast/health")
    assert resp_health.status_code in (200, 500)

    resp_features = client.post(
        "/api/features/online",
        json={"entity_rows": [{"customer_id": "C123"}]},
    )
    assert resp_features.status_code in (200, 500)