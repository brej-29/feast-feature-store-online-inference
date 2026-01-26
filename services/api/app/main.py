import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from feast import FeatureStore
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from services.streaming.feast_push import push_customer_realtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.api")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

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

PREDICT_FEATURE_FETCH_LATENCY = Histogram(
    "predict_feature_fetch_latency_seconds",
    "Latency of Feast feature retrieval in /api/predict.",
)

PREDICT_MODEL_LATENCY = Histogram(
    "predict_model_latency_seconds",
    "Latency of model scoring in /api/predict.",
)

# ---------------------------------------------------------------------------
# Global configuration and singletons
# ---------------------------------------------------------------------------

_FEATURE_STORE: Optional[FeatureStore] = None
_MODEL: Optional[Any] = None
_MODEL_METADATA: Optional[Dict[str, Any]] = None

FEAST_REPO_PATH = os.getenv("FEAST_REPO_PATH", "feature_repo")
MODEL_DIR = os.getenv("MODEL_DIR", "models")
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(MODEL_DIR, "model.joblib"))
MODEL_METADATA_PATH = os.getenv(
    "MODEL_METADATA_PATH",
    os.path.join(MODEL_DIR, "model_metadata.json"),
)
FEATURE_SERVICE_NAME = os.getenv("FEATURE_SERVICE_NAME", "risk_scoring_v1")

TYPE_CODE_MAPPING: Dict[str, int] = {
    "PAYMENT": 1,
    "TRANSFER": 2,
    "CASH_OUT": 3,
    "CASH_IN": 4,
    "DEBIT": 5,
}


def _log_startup_config() -> None:
    logger.info(
        "api_startup_config",
        extra={
            "feast_repo_path": FEAST_REPO_PATH,
            "postgres_host": os.getenv("POSTGRES_HOST") or "",
            "postgres_db": os.getenv("POSTGRES_DB") or "",
            "kafka_brokers": os.getenv("KAFKA_BROKERS") or "",
            "model_path": MODEL_PATH,
            "feature_service_name": FEATURE_SERVICE_NAME,
        },
    )


_log_startup_config()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class EntityIDs(BaseModel):
    customer_id: str
    merchant_id: str
    device_id: str
    account_id: str
    geo_cell_id: str


class PredictionRequest(BaseModel):
    entity_ids: EntityIDs
    amount: float
    type: str
    event_timestamp: Optional[datetime] = None
    isFlaggedFraud: int = 0


class LatencyBreakdown(BaseModel):
    feature_fetch_ms: float
    model_ms: float
    total_ms: float


class PredictionResponse(BaseModel):
    prediction: int = Field(..., description="Binary prediction: 1=fraud, 0=non-fraud.")
    proba: float = Field(..., description="Estimated fraud probability in [0, 1].")
    model_version: str
    latency_ms: LatencyBreakdown
    feature_service: str


class OnlineFeaturesEntityRow(BaseModel):
    customer_id: str
    merchant_id: Optional[str] = None
    device_id: Optional[str] = None
    account_id: Optional[str] = None
    geo_cell_id: Optional[str] = None


class OnlineFeaturesRequest(BaseModel):
    entity_rows: List[OnlineFeaturesEntityRow]


class PushEvent(BaseModel):
    customer_id: str
    amount: float
    type: str
    event_timestamp: Optional[datetime] = None
    isFlaggedFraud: int = 0


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Feast Fraud Feature Store API",
    version="0.1.0",
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


def get_model() -> Tuple[Any, Dict[str, Any]]:
    global _MODEL, _MODEL_METADATA
    if _MODEL is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model artifact not found at {MODEL_PATH}. "
                "Run pipelines/train_model.py to train and export the model.",
            )
        _MODEL = joblib.load(MODEL_PATH)
        if os.path.exists(MODEL_METADATA_PATH):
            with open(MODEL_METADATA_PATH, "r", encoding="utf-8") as f:
                _MODEL_METADATA = json.load(f)
        else:
            _MODEL_METADATA = {}
        logger.info(
            "model_loaded",
            extra={"model_path": MODEL_PATH, "metadata_path": MODEL_METADATA_PATH},
        )
    return _MODEL, _MODEL_METADATA or {}


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Health and metrics endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Lightweight health check endpoint for container/process health.
    """
    logger.info("health_check", extra={"status": "ok"})
    return {"status": "ok"}


@app.get("/api/health")
async def api_health() -> Dict[str, str]:
    """
    API-scoped health check. Mirrors /health but lives under /api/.
    """
    logger.info("api_health_check", extra={"status": "ok"})
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """
    Expose Prometheus metrics for scraping.
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Prediction endpoint
# ---------------------------------------------------------------------------


@app.post("/api/predict", response_model=PredictionResponse)
async def predict(payload: PredictionRequest) -> PredictionResponse:
    """
    Production-style prediction endpoint.

    - Fetches features from Feast using the `risk_scoring_v1` FeatureService
      (configurable via FEATURE_SERVICE_NAME).
    - Applies the trained logistic regression model from `models/model.joblib`.
    - Returns prediction, probability, and latency breakdowns.
    """
    start_total = time.perf_counter()
    event_ts = payload.event_timestamp or datetime.now(timezone.utc)

    # Feature store
    try:
        store = get_feature_store()
    except Exception as exc:  # noqa: BLE001
        logger.exception("feature_store_init_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail=(
                "Feature store not available. Ensure FEAST_REPO_PATH is correct and "
                "run 'feast apply' before calling /api/predict."
            ),
        ) from exc

    # Model
    try:
        model, metadata = get_model()
    except FileNotFoundError as exc:
        logger.warning(
            "model_missing_for_predict",
            extra={"model_path": MODEL_PATH},
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Model artifact not found. Train a model with "
                "'pipelines/train_model.py' before calling /api/predict."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("model_load_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Failed to load model artifact.",
        ) from exc

    # Entity row for Feast
    entity_row = {
        "customer_id": payload.entity_ids.customer_id,
        "merchant_id": payload.entity_ids.merchant_id,
        "device_id": payload.entity_ids.device_id,
        "account_id": payload.entity_ids.account_id,
        "geo_cell_id": payload.entity_ids.geo_cell_id,
    }

    # Request data for OnDemandFeatureView
    request_data = {
        "transaction_request": {
            "amount": [float(payload.amount)],
            "type": [payload.type],
            "event_timestamp": [event_ts],
            "isFlaggedFraud": [int(payload.isFlaggedFraud)],
        },
    }

    # Fetch features from Feast
    start_fetch = time.perf_counter()
    try:
        feature_service = store.get_feature_service(FEATURE_SERVICE_NAME)
        feature_vector = store.get_online_features(
            features=feature_service,
            entity_rows=[entity_row],
            request_data=request_data,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.exception("feast_online_features_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail=(
                "Failed to fetch online features. Ensure Feast has been applied and "
                "materialized, and that the online store is reachable."
            ),
        ) from exc
    feature_fetch_ms = (time.perf_counter() - start_fetch) * 1000.0
    PREDICT_FEATURE_FETCH_LATENCY.observe(feature_fetch_ms / 1000.0)

    # Build model input from Feast features
    feature_cols = metadata.get("feature_columns", [])
    if not feature_cols:
        raise HTTPException(
            status_code=500,
            detail="Model metadata is missing 'feature_columns'; retrain the model.",
        )

    df_features = pd.DataFrame(feature_vector)
    for col in feature_cols:
        if col not in df_features.columns:
            df_features[col] = 0.0
    X = df_features[feature_cols].fillna(0.0)

    # Score model
    start_model = time.perf_counter()
    try:
        proba = float(model.predict_proba(X)[:, 1][0])
    except Exception as exc:  # noqa: BLE001
        logger.exception("model_inference_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Model inference failed.",
        ) from exc
    model_ms = (time.perf_counter() - start_model) * 1000.0
    PREDICT_MODEL_LATENCY.observe(model_ms / 1000.0)

    threshold = float(metadata.get("decision_threshold", 0.5))
    prediction = int(proba >= threshold)
    total_ms = (time.perf_counter() - start_total) * 1000.0

    latency = LatencyBreakdown(
        feature_fetch_ms=feature_fetch_ms,
        model_ms=model_ms,
        total_ms=total_ms,
    )

    logger.info(
        "prediction",
        extra={
            "prediction": prediction,
            "proba": proba,
            "threshold": threshold,
            "feature_service": FEATURE_SERVICE_NAME,
            "latency_ms": total_ms,
        },
    )

    return PredictionResponse(
        prediction=prediction,
        proba=proba,
        model_version=metadata.get("model_version", "unknown"),
        latency_ms=latency,
        feature_service=FEATURE_SERVICE_NAME,
    )


# ---------------------------------------------------------------------------
# Feast health and debug endpoints
# ---------------------------------------------------------------------------


@app.get("/api/feast/health")
async def feast_health() -> Dict[str, Any]:
    """
    Health check for Feast integration.

    Attempts to initialize the FeatureStore and list entities and feature services.
    """
    try:
        store = get_feature_store()
        entities = store.list_entities()
        services = store.list_feature_services()
        logger.info(
            "feast_health_ok",
            extra={
                "entity_count": len(entities),
                "feature_service_count": len(services),
            },
        )
        return {
            "status": "ok",
            "entities": [e.name for e in entities],
            "feature_services": [s.name for s in services],
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("feast_health_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail=(
                "Feast feature store not available; check registry, Postgres "
                "configuration, and FEAST_REPO_PATH."
            ),
        ) from exc


@app.post("/api/features/online")
async def get_online_features(body: OnlineFeaturesRequest) -> Dict[str, Any]:
    """
    Fetch online features for a list of entity rows.

    This is a debug endpoint used to validate end-to-end Feast + Postgres wiring.
    It gracefully returns 5xx errors if the feature store or online store is not
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

    entity_dicts = [row.dict(exclude_none=True) for row in body.entity_rows]

    try:
        # Keep this endpoint simple by using the baseline customer profile +
        # realtime FeatureView set.
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


# ---------------------------------------------------------------------------
# Realtime push endpoint (mirrors the Kafka consumer path)
# ---------------------------------------------------------------------------


@app.post("/api/push")
async def push_realtime(event: PushEvent) -> Dict[str, Any]:
    """
    Push a single realtime customer event into Feast via the PushSource.

    This mirrors the transformation done by the Kafka consumer and is useful for
    manual testing or simple integrations that don't use Kafka.
    """
    ts = (event.event_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
    type_code = TYPE_CODE_MAPPING.get(event.type.upper(), 0)

    df = pd.DataFrame(
        [
            {
                "event_timestamp": ts,
                "customer_id": event.customer_id,
                "last_txn_amount": float(event.amount),
                "last_txn_type_code": int(type_code),
                "last_txn_hour": int(ts.hour),
                "last_txn_is_flagged": int(event.isFlaggedFraud),
            },
        ],
    )

    try:
        push_customer_realtime(df)
    except Exception as exc:  # noqa: BLE001
        logger.exception("feast_push_realtime_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Failed to push realtime features to Feast; check logs for details.",
        ) from exc

    logger.info(
        "feast_push_realtime_ok",
        extra={
            "customer_id": event.customer_id,
            "amount": float(event.amount),
            "type": event.type,
        },
    )
    return {"status": "ok", "rows": 1}