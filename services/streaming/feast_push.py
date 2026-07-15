import logging
import os
import time
from typing import Optional

import pandas as pd
from feast import FeatureStore
from prometheus_client import Counter, Gauge, Histogram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.streaming.feast_push")

_FEATURE_STORE: Optional[FeatureStore] = None

PUSH_SUCCESS_TOTAL = Counter(
    "feast_push_success_total", "Successful pushes to the Feast online store."
)
PUSH_FAILURE_TOTAL = Counter(
    "feast_push_failure_total", "Failed pushes to the Feast online store."
)
PUSH_LAST_SUCCESS_UNIXTIME = Gauge(
    "feast_push_last_success_unixtime",
    "Wall-clock time (unix seconds) of the last successful push.",
)
PUSH_EVENT_LAG_SECONDS = Histogram(
    "feast_push_event_lag_seconds",
    "Age of the newest event in a batch at push time -- the streaming "
    "freshness/feature-staleness indicator (Kafka consume + processing lag).",
    buckets=[1, 5, 15, 30, 60, 300, 900, 3600],
)


def get_feature_store() -> FeatureStore:
    global _FEATURE_STORE
    if _FEATURE_STORE is None:
        # Resolve POSTGRES_URL -> discrete POSTGRES_* (incl. sslmode) before
        # building the store, matching the API and Feast CLI paths.
        from pipelines.pg_config import apply_postgres_url_env

        apply_postgres_url_env()
        repo_path = os.getenv("FEAST_REPO_PATH", "feature_repo")
        logger.info("Initializing FeatureStore", extra={"repo_path": repo_path})
        _FEATURE_STORE = FeatureStore(repo_path=repo_path)
    return _FEATURE_STORE


def push_customer_realtime(df: pd.DataFrame) -> None:
    """
    Push a batch of customer-level realtime events into Feast via PushSource.

    Expected columns in df:
    - event_timestamp (datetime)
    - customer_id (str)
    - last_txn_amount (float)
    - last_txn_type_code (int)
    - last_txn_hour (int)
    - last_txn_is_flagged (int)
    """
    if df.empty:
        logger.info("No rows to push to Feast (empty dataframe).")
        return

    try:
        store = get_feature_store()
        logger.info(
            "Pushing realtime customer features to Feast",
            extra={"rows": len(df)},
        )
        store.push("customer_realtime_push", df)
        PUSH_SUCCESS_TOTAL.inc()
        PUSH_LAST_SUCCESS_UNIXTIME.set(time.time())
        newest_event = pd.to_datetime(df["event_timestamp"], utc=True).max()
        lag_seconds = (pd.Timestamp.now(tz="UTC") - newest_event).total_seconds()
        PUSH_EVENT_LAG_SECONDS.observe(max(lag_seconds, 0.0))
    except Exception:
        PUSH_FAILURE_TOTAL.inc()
        logger.exception("feast_push_failed")
        raise
