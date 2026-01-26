import logging
import os
from typing import Optional

import pandas as pd
from feast import FeatureStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feast_fraud.streaming.feast_push")

_FEATURE_STORE: Optional[FeatureStore] = None


def get_feature_store() -> FeatureStore:
    global _FEATURE_STORE
    if _FEATURE_STORE is None:
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
    except Exception:
        logger.exception("feast_push_failed")
        raise