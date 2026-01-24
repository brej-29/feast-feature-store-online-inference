import logging
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
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


class PredictInput(BaseModel):
    entity_ids: Dict[str, Any]
    request: Dict[str, Any]


class PredictOutput(BaseModel):
    fraud_probability: float
    model_version: str
    latency_ms: float
    debug_info: Optional[Dict[str, Any]] = None


app = FastAPI(
    title="Feast Fraud Feature Store API",
    version="0.0.1",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


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