from services.api.app.main import (
    EntityIDs,
    PredictionRequest,
    PredictionResponse,
)


def test_prediction_request_model_roundtrip():
    entity_ids = EntityIDs(
        customer_id="C123",
        merchant_id="M456",
        device_id="D789",
        account_id="A123",
        geo_cell_id="G999",
    )
    req = PredictionRequest(
        entity_ids=entity_ids,
        amount=100.0,
        type="PAYMENT",
        isFlaggedFraud=0,
    )
    assert req.entity_ids.customer_id == "C123"
    assert req.amount == 100.0
    assert req.type == "PAYMENT"

    # Basic response construction smoke test
    latency = {"feature_fetch_ms": 1.0, "model_ms": 2.0, "total_ms": 3.0}
    resp = PredictionResponse(
        prediction=0,
        proba=0.1,
        model_version="test",
        latency_ms=latency,
        feature_service="risk_scoring_v1",
    )
    assert resp.prediction in (0, 1)
    assert 0.0 <= resp.proba <= 1.0