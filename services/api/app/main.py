import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from feast import FeatureStore
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

logger = logging.getLogger("feast_fraud.api")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "Latency of HTTP requests in seconds.",
    ["endpoint"],
)

REQUEST_COUNT = Counter(
    "api_request_count_total",
    "Total count of HTTP requests.",
    ["endpoint", "http_status"],
)

_FEATURE_STORE: Optional[FeatureStore] = None
FEAST_REPO_PATH = os.getenv("FEAST_REPO_PATH", "feature_repo")


class PredictInput(BaseModel):
    entity_ids: Dict[str, Any]
    request: Dict[str, Any]


class PredictOutput(BaseModel):
    fraud_probability: float
    model_version: str
    latency_ms: float
    debug_info: Optional[Dict[str, Any]] = None


class OnlineFeaturesEntityRow(BaseModel):
    customer_id: str


class OnlineFeaturesRequest(BaseModel):
    entity_rows: List[OnlineFeaturesEntityRow]


app = FastAPI(
    title="Feast Fraud Feature Store API",
    version="0.0.1",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


def get_feature_store() -> FeatureStore:
    global _FEATURE_STORE
    if _FEATURE_STORE is None:
        logger.info(
            "Initializing FeatureStore for API usage",
            extra={"repo_path": FEAST_REPO_PATH},
        )
        _FEATURE_STORE = FeatureStore(repo_path=FEAST_REPO_PATH)
    return _FEATURE_STORE


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    Middleware for basic structured logging and Prometheus metrics.

    - Logs each request with method, path, and status.
    - Records latency and status code labels in Prometheus metrics.
    """
    start = time.perf_counter()
    path = request.url.path

    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        process_time = time.perf_counter() - start
        REQUEST_LATENCY.labels(endpoint=path).observe(process_time)
        REQUEST_COUNT.labels(endpoint=path, http_status="500").inc()

        logger.exception(
            "unhandled_exception",
            extra={
                "path": path,
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    process_time = time.perf_counter() - start
    REQUEST_LATENCY.labels(endpoint=path).observe(process_time)
    REQUEST_COUNT.labels(endpoint=path, http_status=str(response.status_code)).inc()

    logger.info(
        "request_completed",
        extra={
            "path": path,
            "method": request.method,
            "status_code": response.status_code,
            "latency_seconds": process_time,
        },
    )
    return response


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Lightweight health check endpoint.

    Returns a static payload that can be used by probes and load balancers.
    """
    logger.info("health_check", extra={"status": "ok"})
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """
    Expose Prometheus metrics for scraping.
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.post("/api/predict", response_model=PredictOutput)
async def predict(payload: PredictInput) -> PredictOutput:
    """
    Stub prediction endpoint.

    Accepts a body of the form:
    {
        "entity_ids": {...},
        "request": {
            "amount": <float>,
            "type": <str>,
            ...
        }
    }

    Returns a fake fraud probability and measures internal latency.
    """
    start = time.perf_counter()

    amount = payload.request.get("amount", 0.0)
    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        amount_value = 0.0

    base_prob = 0.05
    scaled_component = min(amount_value / 100000.0, 0.9)
    fraud_probability = min(0.95, base_prob + scaled_component)

    latency_ms = (time.perf_counter() - start) * 1000.0

    logger.info(
        "prediction_stub",
        extra={
            "fraud_probability": fraud_probability,
            "latency_ms": latency_ms,
            "amount": amount_value,
        },
    )

    return PredictOutput(
        fraud_probability=fraud_probability,
        model_version="stub-0",
        latency_ms=latency_ms,
        debug_info={
            "note": "Stub implementation; replace with real model and Feast features.",
        },
    )


@app.get("/api/feast/health")
async def feast_health() -> Dict[str, str]:
    """
    Health check for Feast integration.

    Attempts to initialize the FeatureStore and list entities.
    """
    try:
        store = get_feature_store()
        entities = store.list_entities()
        logger.info(
            "feast_health_ok",
            extra={"entity_count": len(entities)},
        )
        return {"status": "ok", "entities": [e.name for e in entities]}
    except Exception as exc:  # noqa: BLE001
        logger.exception("feast_health_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Feast feature store not available; check registry and Postgres configuration.",
        ) from exc


@app.post("/api/features/online")
async def get_online_features(body: OnlineFeaturesRequest) -> Dict[str, Any]:
    """
    Fetch online features for a list of customer entity rows.

    This is a minimal endpoint used to validate end-to-end Feast + Postgres wiring.
    It gracefully returns 500 errors if the feature store or online store is not
    available, so tests do not require Postgres to be running.
    """
    if not body.entity_rows:
        raise HTTPException(status_code=400, detail="entity_rows must not be empty")

    try:
        store = get_feature_store()
    except Exception as exc:  # noqa: BLE001
        logger.exception("feature_store_init_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize FeatureStore; ensure registry and configuration exist.",
        ) from exc

    entity_dicts = [row.dict() for row in body.entity_rows]

    try:
        feature_names = [
            "customer_profile_v1:txn_count_total",
            "customer_profile_v1:amount_sum_total",
            "customer_profile_v1:amount_mean",
            "customer_profile_v1:amount_max",
            "customer_profile_v1:fraud_rate",
            "customer_profile_v1:flagged_rate",
            "customer_profile_v1:unique_counterparty_count",
            "customer_realtime_v1:last_txn_amount",
            "customer_realtime_v1:last_txn_type_code",
            "customer_realtime_v1:last_txn_hour",
            "customer_realtime_v1:last_txn_is_flagged",
        ]

        result = store.get_online_features(
            features=feature_names,
            entity_rows=entity_dicts,
        ).to_dict()

        logger.info(
            "online_features_fetched",
            extra={"entity_count": len(entity_dicts)},
        )

        return {"features": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_online_features_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch online features; ensure Feast has been applied and materialized.",
        ) from exc