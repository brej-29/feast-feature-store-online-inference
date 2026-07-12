"""Tests for the /api/predict serving path with mocked model and store."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression

import services.api.app.main as api_main
from services.api.app.main import app

client = TestClient(app)

FEAST_FEATURES = [
    "customer_profile_v2__txn_count_prior",
    "customer_profile_v2__fraud_rate_prior",
    "customer_realtime_v1__last_txn_hour",
]
REQUEST_FEATURES = [
    "amount",
    "type_code",
    "txn_hour",
    "oldbalanceOrg",
    "oldbalanceDest",
    "amount_over_orig_balance",
]
FEATURE_NAMES = REQUEST_FEATURES + FEAST_FEATURES


@pytest.fixture()
def model_bundle(monkeypatch):
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(200, len(FEATURE_NAMES))), columns=FEATURE_NAMES)
    y = (X["amount"] > 0).astype(int)
    model = LogisticRegression().fit(X, y)
    bundle = {
        "model": model,
        "model_version": "test_v0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_names": FEATURE_NAMES,
        "request_feature_names": REQUEST_FEATURES,
        "feast_feature_names": FEAST_FEATURES,
        "feature_service": "fraud_detection_v2",
        "feature_defaults": {name: 0.0 for name in FEATURE_NAMES}
        | {"customer_realtime_v1__last_txn_hour": -1.0},
        "threshold": 0.5,
        "metrics": {"pr_auc": 0.5},
    }
    monkeypatch.setattr(api_main, "_MODEL_BUNDLE", bundle)
    yield bundle
    monkeypatch.setattr(api_main, "_MODEL_BUNDLE", None)


PAYLOAD = {
    "entity_ids": {"customer_id": "C123", "merchant_id": "M456"},
    "request": {"amount": 5000.0, "type": "TRANSFER", "oldbalanceOrg": 100.0},
}


def test_predict_with_online_features(model_bundle, monkeypatch):
    def fake_fetch(store, bundle, entity_row):
        assert set(entity_row) == {
            "customer_id",
            "merchant_id",
            "account_id",
            "geo_cell_id",
            "device_id",
        }
        return {
            "customer_profile_v2__txn_count_prior": 4.0,
            "customer_profile_v2__fraud_rate_prior": 0.25,
            "customer_realtime_v1__last_txn_hour": None,  # missing online value
        }

    monkeypatch.setattr(api_main, "get_feature_store", lambda: object())
    monkeypatch.setattr(api_main, "_fetch_online_features", fake_fetch)

    response = client.post("/api/predict", json=PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["fraud_probability"] <= 1.0
    assert body["model_version"] == "test_v0"
    assert body["debug_info"]["degraded"] is False
    # The None online value must fall back to the training-time default.
    assert body["debug_info"]["missing_feature_count"] == 1
    assert body["feature_fetch_ms"] >= 0.0
    assert body["inference_ms"] >= 0.0


def test_predict_degrades_when_store_unavailable(model_bundle, monkeypatch):
    def broken_store():
        raise RuntimeError("online store down")

    monkeypatch.setattr(api_main, "get_feature_store", broken_store)

    response = client.post("/api/predict", json=PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["debug_info"]["degraded"] is True
    assert body["debug_info"]["missing_feature_count"] == len(FEAST_FEATURES)


def test_predict_requires_entity_ids(model_bundle):
    response = client.post(
        "/api/predict", json={"entity_ids": {}, "request": {"amount": 10}}
    )
    assert response.status_code == 400


def test_predict_503_when_model_missing(monkeypatch):
    monkeypatch.setattr(api_main, "_MODEL_BUNDLE", None)
    monkeypatch.setattr(api_main, "MODEL_PATH", "does/not/exist.joblib")
    response = client.post("/api/predict", json=PAYLOAD)
    assert response.status_code == 503


def test_model_info(model_bundle):
    response = client.get("/api/model/info")
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "test_v0"
    assert body["n_feast_features"] == len(FEAST_FEATURES)


def test_predict_allowed_without_api_key_when_unset(model_bundle, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(
        api_main, "get_feature_store", lambda: (_ for _ in ()).throw(RuntimeError("no store"))
    )
    response = client.post("/api/predict", json=PAYLOAD)
    assert response.status_code == 200


def test_predict_rejects_missing_or_wrong_api_key(model_bundle, monkeypatch):
    # No store/feature mocking needed: the API-key dependency runs before the
    # route body, so these requests never reach the (network-touching) store.
    monkeypatch.setenv("API_KEY", "secret123")
    response = client.post("/api/predict", json=PAYLOAD)
    assert response.status_code == 401
    assert response.json()["request_id"]

    response = client.post(
        "/api/predict", json=PAYLOAD, headers={"X-API-Key": "wrong"}
    )
    assert response.status_code == 401


def test_predict_allows_correct_api_key(model_bundle, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    monkeypatch.setattr(
        api_main, "get_feature_store", lambda: (_ for _ in ()).throw(RuntimeError("no store"))
    )
    response = client.post(
        "/api/predict", json=PAYLOAD, headers={"X-API-Key": "secret123"}
    )
    assert response.status_code == 200
