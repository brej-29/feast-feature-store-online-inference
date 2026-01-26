import os

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import MODEL_PATH, app

client = TestClient(app)


@pytest.mark.skipif(
    not os.path.exists(MODEL_PATH),
    reason="Model artifact missing; run pipelines/train_model.py before this test.",
)
def test_predict_route_smoke_with_model():
    payload = {
        "entity_ids": {
            "customer_id": "C123",
            "merchant_id": "M456",
            "device_id": "D789",
            "account_id": "A123",
            "geo_cell_id": "G999",
        },
        "amount": 100.0,
        "type": "PAYMENT",
        "isFlaggedFraud": 0,
    }

    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "proba" in data
    assert "prediction" in data