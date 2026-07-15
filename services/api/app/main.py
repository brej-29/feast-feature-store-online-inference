import contextvars
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from feast import FeatureStore
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

from pipelines.encoders import deterministic_hash, map_type_to_code
from pipelines.pg_config import apply_postgres_url_env

# Resolve POSTGRES_URL -> discrete POSTGRES_* env vars (incl. sslmode) before
# any FeatureStore is constructed, so feature_store.yaml substitution sees the
# managed-DB connection rather than a stale local default.
apply_postgres_url_env()

logger = logging.getLogger("feast_fraud.api")

# Correlation ID for the request currently being handled on this async task.
# Propagates through awaited calls within the same request without needing to
# thread an argument through every function; defaults to "-" for log lines
# emitted outside a request (startup, background pipelines, etc.).
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
)
# Attach to the handler (not the root logger) so it fires for every record
# that reaches it regardless of which named logger emitted it -- logger-level
# filters only run for the originating logger, not for records propagated up
# from child loggers like "feast_fraud.api".
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_RequestIdFilter())


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

FEATURE_FETCH_LATENCY = Histogram(
    "predict_feature_fetch_seconds",
    "Latency of online feature retrieval from the Feast online store.",
)

INFERENCE_LATENCY = Histogram(
    "predict_inference_seconds",
    "Latency of model inference.",
)

PREDICTION_SCORE = Histogram(
    "predict_fraud_probability",
    "Distribution of predicted fraud probabilities.",
    buckets=[0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
)

DEGRADED_PREDICTIONS = Counter(
    "predict_degraded_total",
    "Predictions served without online features (feature store unavailable).",
)

_FEATURE_STORE: Optional[FeatureStore] = None
_MODEL_BUNDLE: Optional[Dict[str, Any]] = None

FEAST_REPO_PATH = os.getenv("FEAST_REPO_PATH", "feature_repo")
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join("models", "fraud_model_v2.joblib"))

# If API_KEY is unset, auth is disabled (local dev / tests). If set, callers
# must send a matching X-API-Key header. Read at request time (not import
# time) so tests can toggle it via monkeypatch/env without reimporting.
def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class PredictInput(BaseModel):
    entity_ids: Dict[str, Any]
    request: Dict[str, Any]


class PredictOutput(BaseModel):
    fraud_probability: float
    is_fraud: bool
    threshold: float
    model_version: str
    latency_ms: float
    feature_fetch_ms: float
    inference_ms: float
    debug_info: Optional[Dict[str, Any]] = None


class OnlineFeaturesEntityRow(BaseModel):
    customer_id: str


class OnlineFeaturesRequest(BaseModel):
    entity_rows: List[OnlineFeaturesEntityRow]


app = FastAPI(
    title="Feast Fraud Feature Store API",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Include the request correlation ID on every HTTPException response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id_var.get()},
        headers=exc.headers,
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


def get_model_bundle() -> Dict[str, Any]:
    """Load the trained model bundle (model + feature contract) lazily.

    The bundle carries the exact feature names/order used at training time,
    plus per-feature defaults, so serving cannot silently drift from training.
    """
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model artifact not found at {MODEL_PATH}. "
                "Run pipelines/train_model.py first."
            )
        logger.info("Loading model bundle", extra={"model_path": MODEL_PATH})
        _MODEL_BUNDLE = joblib.load(MODEL_PATH)
    return _MODEL_BUNDLE


def _derive_entity_ids(entity_ids: Dict[str, Any]) -> Dict[str, str]:
    """Derive the full entity key set from what the caller provided.

    Mirrors pipelines/data_ingest.py exactly: account == origin customer,
    geo cell and device are deterministic hashes. Accepts either canonical
    ids (customer_id/merchant_id) or raw Kaggle-style names
    (nameOrig/nameDest).
    """
    customer_id = str(entity_ids.get("customer_id") or entity_ids.get("nameOrig") or "")
    merchant_id = str(entity_ids.get("merchant_id") or entity_ids.get("nameDest") or "")
    if not customer_id or not merchant_id:
        raise HTTPException(
            status_code=400,
            detail="entity_ids must include customer_id/nameOrig and merchant_id/nameDest.",
        )
    return {
        "customer_id": customer_id,
        "merchant_id": merchant_id,
        "account_id": str(entity_ids.get("account_id") or customer_id),
        "geo_cell_id": str(entity_ids.get("geo_cell_id") or deterministic_hash(merchant_id)),
        "device_id": str(
            entity_ids.get("device_id")
            or deterministic_hash(f"{customer_id}|{merchant_id}")
        ),
    }


def _build_request_features(request: Dict[str, Any]) -> Dict[str, float]:
    """Features computed from the request payload itself (no store lookup).

    Must mirror pipelines/train_model.py::build_entity_df.
    """

    def _num(key: str, default: float = 0.0) -> float:
        try:
            return float(request.get(key, default))
        except (TypeError, ValueError):
            return default

    amount = _num("amount")
    oldbalance_org = _num("oldbalanceOrg")
    oldbalance_dest = _num("oldbalanceDest")
    return {
        "amount": amount,
        "type_code": float(map_type_to_code(str(request.get("type", "")))),
        "txn_hour": float(datetime.now(timezone.utc).hour),
        "oldbalanceOrg": oldbalance_org,
        "oldbalanceDest": oldbalance_dest,
        "amount_over_orig_balance": amount / (oldbalance_org + 1.0),
    }


def _fetch_online_features(
    store: FeatureStore,
    bundle: Dict[str, Any],
    entity_row: Dict[str, str],
) -> Dict[str, Optional[float]]:
    service = store.get_feature_service(bundle["feature_service"])
    result = store.get_online_features(
        features=service,
        entity_rows=[entity_row],
        full_feature_names=True,
    ).to_dict()
    return {
        name: (values[0] if values else None)
        for name, values in result.items()
        if name in set(bundle["feast_feature_names"])
    }


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    Middleware for request correlation, structured logging, and Prometheus metrics.

    - Assigns/propagates a request ID (X-Request-ID) for log correlation.
    - Logs each request with method, path, and status.
    - Records latency and status code labels in Prometheus metrics.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)

    start = time.perf_counter()
    path = request.url.path

    try:
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
                content={"detail": "Internal server error", "request_id": request_id},
                headers={"X-Request-ID": request_id},
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
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Lightweight health check endpoint.

    Returns a static payload that can be used by probes and load balancers.
    """
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """
    Expose Prometheus metrics for scraping.
    """
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/api/model/info")
async def model_info() -> Dict[str, Any]:
    """Metadata about the currently served model (version, metrics, features)."""
    try:
        bundle = get_model_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "model_version": bundle["model_version"],
        "trained_at": bundle["trained_at"],
        "threshold": bundle["threshold"],
        "feature_service": bundle["feature_service"],
        "n_request_features": len(bundle["request_feature_names"]),
        "n_feast_features": len(bundle["feast_feature_names"]),
        "metrics": bundle["metrics"],
    }


@app.post("/api/predict", response_model=PredictOutput, dependencies=[Depends(require_api_key)])
async def predict(payload: PredictInput) -> PredictOutput:
    """Score a transaction for fraud.

    Flow: derive entity keys -> fetch online features from the Feast online
    store -> assemble the feature vector in the training-time order -> model
    inference. If the online store is unavailable the endpoint degrades to
    request-time features plus training defaults and flags the response.
    """
    start = time.perf_counter()

    try:
        bundle = get_model_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    entity_row = _derive_entity_ids(payload.entity_ids)
    request_features = _build_request_features(payload.request)

    degraded = False
    online_features: Dict[str, Optional[float]] = {}
    fetch_start = time.perf_counter()
    try:
        store = get_feature_store()
        online_features = _fetch_online_features(store, bundle, entity_row)
    except Exception:  # noqa: BLE001
        logger.exception("online_feature_fetch_failed", extra={"entity_row": entity_row})
        degraded = True
        DEGRADED_PREDICTIONS.inc()
    feature_fetch_s = time.perf_counter() - fetch_start
    FEATURE_FETCH_LATENCY.observe(feature_fetch_s)

    defaults = bundle["feature_defaults"]
    missing: List[str] = []
    row: Dict[str, float] = {}
    for name in bundle["feature_names"]:
        if name in request_features:
            row[name] = request_features[name]
        else:
            value = online_features.get(name)
            if value is None:
                missing.append(name)
                value = defaults.get(name, 0.0)
            row[name] = float(value)

    inference_start = time.perf_counter()
    features_frame = pd.DataFrame([row], columns=bundle["feature_names"])
    fraud_probability = float(bundle["model"].predict_proba(features_frame)[0, 1])
    inference_s = time.perf_counter() - inference_start
    INFERENCE_LATENCY.observe(inference_s)
    PREDICTION_SCORE.observe(fraud_probability)

    threshold = float(bundle["threshold"])
    latency_ms = (time.perf_counter() - start) * 1000.0

    logger.info(
        "prediction_served",
        extra={
            "fraud_probability": round(fraud_probability, 6),
            "model_version": bundle["model_version"],
            "degraded": degraded,
            "missing_features": len(missing),
            "latency_ms": round(latency_ms, 2),
        },
    )

    return PredictOutput(
        fraud_probability=fraud_probability,
        is_fraud=fraud_probability >= threshold,
        threshold=threshold,
        model_version=bundle["model_version"],
        latency_ms=latency_ms,
        feature_fetch_ms=feature_fetch_s * 1000.0,
        inference_ms=inference_s * 1000.0,
        debug_info={
            "degraded": degraded,
            "entity_ids": entity_row,
            "missing_feature_count": len(missing),
            "missing_features": missing[:20],
        },
    )


@app.get("/api/feast/health")
async def feast_health() -> Dict[str, Any]:
    """
    Health check for Feast integration.

    Attempts to initialize the FeatureStore and list entities.
    """
    try:
        store = get_feature_store()
        entities = store.list_entities()
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

    Used to inspect what the online store currently holds for an entity
    (e.g., to watch realtime features update as Kafka events are pushed).
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
            "customer_profile_v2:txn_count_prior",
            "customer_profile_v2:amount_sum_prior",
            "customer_profile_v2:amount_mean_prior",
            "customer_profile_v2:amount_max_prior",
            "customer_profile_v2:unique_counterparty_count_prior",
            "customer_profile_v2:flagged_rate_prior",
            "customer_profile_v2:fraud_rate_prior",
            "customer_realtime_v1:last_txn_amount",
            "customer_realtime_v1:last_txn_type_code",
            "customer_realtime_v1:last_txn_hour",
            "customer_realtime_v1:last_txn_is_flagged",
        ]

        result = store.get_online_features(
            features=feature_names,
            entity_rows=entity_dicts,
        ).to_dict()

        return {"features": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_online_features_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch online features; ensure Feast has been applied and materialized.",
        ) from exc
